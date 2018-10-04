import io

import urllib3
from bitarray import bitarray
import base64
import struct
from structlog import get_logger
from flask import Response

from entityservice import app
from entityservice.object_store import connect_to_object_store
from entityservice.settings import Config as config
from entityservice.utils import chunks, safe_fail_request, iterable_to_stream
import concurrent.futures


logger = get_logger()


def bytes_to_list(python_object):
    if isinstance(python_object, bytes):
        return list(python_object)
    raise TypeError(repr(python_object) + ' is not serializable as a list')


def list_to_bytes(python_object):
    if isinstance(python_object, list):
        return bytes(python_object)
    raise TypeError(repr(python_object) + ' is not valid bytes')


def deserialize_bitarray(bytes_data):
    ba = bitarray(endian='big')
    data_as_bytes = base64.decodebytes(bytes_data.encode())
    ba.frombytes(data_as_bytes)
    return ba


"""
The binary format used:

- "!" Use network byte order (big-endian).
- "1I" Store the index in 4 bytes as an unsigned int.
- "128s" Store the 128 raw bytes of the bitarray
- "1H" The popcount stored in 2 bytes (unsigned short)

https://docs.python.org/3/library/struct.html#format-strings
"""
bit_packing_fmt = "!1I128s1H"
bit_packed_element_size = struct.calcsize(bit_packing_fmt)


def binary_pack_filters(filters):
    """Efficient packing of bloomfilters with index and popcount.

    :param filters:
        An iterable of tuples as produced by deserialize_filters.

    :return:
        An iterable of bytes.
    """
    for ba_clk, indx, count in filters:
        yield struct.pack(
          bit_packing_fmt,
          indx,
          ba_clk.tobytes(),
          count
        )


def binary_unpack_one(data):
    index, clk_bytes, count = struct.unpack(bit_packing_fmt, data)
    assert len(clk_bytes) == 128

    ba = bitarray(endian="big")
    ba.frombytes(clk_bytes)
    return ba, index, count


def binary_unpack_filters(streamable_data, max_bytes=None):
    filters = []
    bytes_consumed = 0
    for raw_bytes in streamable_data.stream(bit_packed_element_size):
        assert len(raw_bytes) == 134
        filters.append(binary_unpack_one(raw_bytes))

        bytes_consumed += bit_packed_element_size
        if max_bytes is not None and bytes_consumed >= max_bytes:
            break

    return filters


def deserialize_filters(filters):
    """
    Deserialize iterable of base64 encoded clks.

    Carrying out the popcount and adding the index as we go.
    """
    res = []
    for i, f in enumerate(filters):
        ba = deserialize_bitarray(f)
        res.append((ba, i, ba.count()))
    return res


def deserialize_filters_concurrent(filters):
    """
    Deserialize iterable of base64 encoded clks.

    Carrying out the popcount and adding the index as we go.
    """
    res = []
    chunk_size = int(100000)
    with concurrent.futures.ProcessPoolExecutor() as executor:
        futures = []
        for i, chunk in enumerate(chunks(filters, chunk_size)):
            future = executor.submit(deserialize_filters, chunk)
            futures.append(future)

        for future in futures:
            res.extend(future.result())

    return res


def generate_scores(csv_text_stream):
    """
    Processes a TextIO stream of csv similarity scores into
    a json generator.

    """
    yield '{"similarity_scores": ['
    line_iter = csv_text_stream.__iter__()

    try:
        prev_line = next(line_iter)
    except StopIteration:
        # Must have been an empty file, so close json object and stop iteration
        yield "]}"
        return

    for line in line_iter:
        yield '[{}],'.format(prev_line.strip())
        prev_line = line

    # Yield the last line without a trailing comma, instead close the json object
    yield '[{}]'.format(prev_line.strip())
    yield ']}'


def get_similarity_scores(filename):
    """
    Read a CSV file from the object store containing the similarity scores and return
    a response that will stream the similarity scores.

    :param filename: name of the CSV file, obtained from the `similarity_scores` table
    :return: the similarity scores in a streaming JSON response.
    """

    mc = connect_to_object_store()

    details = mc.stat_object(config.MINIO_BUCKET, filename)
    logger.info("Starting download stream of similarity scores.", filename=filename, filesize=details.size)

    try:
        csv_data_stream = iterable_to_stream(mc.get_object(config.MINIO_BUCKET, filename).stream())

        # Process the CSV into JSON
        csv_text_stream = io.TextIOWrapper(csv_data_stream, encoding="utf-8")

        return Response(generate_scores(csv_text_stream), mimetype='application/json')

    except urllib3.exceptions.ResponseError:
        logger.warning("Attempt to read the similarity scores file failed with an error response.", filename=filename)
        safe_fail_request(500, "Failed to retrieve similarity scores")
