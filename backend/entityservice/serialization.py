
import typing
import urllib3

import base64
import struct

import anonlink
from flask import Response
from structlog import get_logger

from entityservice.object_store import connect_to_object_store
from entityservice.settings import Config as config
from entityservice.utils import chunks, safe_fail_request
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


def deserialize_bytes(bytes_data):
    return base64.b64decode(bytes_data)


def binary_format(encoding_size):
    """
    Return a Struct instance with the binary format of the encodings.

    The binary format string can be understood as:
    - "!" Use network byte order (big-endian).
    - "I" store the entity ID as an unsigned int
    - "<encoding size>s" Store the n (e.g. 128) raw bytes of the bitarray

    https://docs.python.org/3/library/struct.html

    :param encoding_size: the encoding size of one filter in number of bytes, excluding the entity ID info
    :return:
        A Struct object which can read and write the binary format.
    """
    bit_packing_fmt = f"!I{encoding_size}s"
    bit_packing_struct = struct.Struct(bit_packing_fmt)
    return bit_packing_struct


def binary_pack_filters(filters, encoding_size):
    """Efficient packing of bloomfilters.

    :param filters:
        An iterable of tuples, with
            - first element is the entity ID as an unsigned int
            - second element is 'encoding_size' number of bytes as produced by deserialize_bytes.
    :param encoding_size: the encoding size of one filter in number of bytes, excluding the entity ID info
    :return:
        An iterable of bytes.
    """
    bit_packing_struct = binary_format(encoding_size)

    for hash_bytes in filters:
        yield bit_packing_struct.pack(*hash_bytes)


def binary_unpack_one(data, bit_packing_struct):
    entity_id, clk_bytes, = bit_packing_struct.unpack(data)
    return entity_id, clk_bytes


def binary_unpack_filters(data_iterable, max_bytes=None, encoding_size=None):
    """
    Unpack filters that were packed with the 'binary_pack_filters' method.

    :param data_iterable: an iterable of binary packed filters.
    :param max_bytes: if present, only read up to 'max_bytes' bytes.
    :param encoding_size: the encoding size of one filter in number of bytes, excluding the entity ID info
    :return: list of filters with their corresponding entity IDs as a list of tuples.
    """
    assert encoding_size is not None
    bit_packed_element = binary_format(encoding_size)
    bit_packed_element_size = bit_packed_element.size
    filters = []
    bytes_consumed = 0

    logger.debug(f"Iterating over encodings of size {encoding_size} - packed as {bit_packed_element_size}")
    for raw_bytes in data_iterable:
        filters.append(binary_unpack_one(raw_bytes, bit_packed_element))

        bytes_consumed += bit_packed_element_size
        if max_bytes is not None and bytes_consumed >= max_bytes:
            break

    return filters


def generate_scores(candidate_pair_stream: typing.BinaryIO):
    """
    Processes a TextIO stream of candidate pair similarity scores into
    a json generator.
    """
    sims, (dset_is0, dset_is1), (rec_is0, rec_is1) = anonlink.serialization.load_candidate_pairs(candidate_pair_stream)

    cs_sims_iter = (f'[{dset_i0}, {rec_i0}], [{dset_i1}, {rec_i1}], {sim}'
                    for sim, dset_i0, dset_i1, rec_i0, rec_i1 in zip(sims, dset_is0, dset_is1, rec_is0, rec_is1))
    yield '{"similarity_scores": ['
    line_iter = iter(cs_sims_iter)

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
        candidate_pair_binary_stream = mc.get_object(config.MINIO_BUCKET, filename)

        return Response(generate_scores(candidate_pair_binary_stream), mimetype='application/json')

    except urllib3.exceptions.ResponseError:
        logger.warning("Attempt to read the similarity scores file failed with an error response.", filename=filename)
        safe_fail_request(500, "Failed to retrieve similarity scores")


def get_chunk_from_object_store(chunk_info, encoding_size=128):
    mc = connect_to_object_store()
    bit_packed_element_size = binary_format(encoding_size).size
    chunk_range_start, chunk_range_stop = chunk_info['range']
    chunk_length = chunk_range_stop - chunk_range_start
    chunk_bytes = bit_packed_element_size * chunk_length
    chunk_stream = mc.get_partial_object(
        config.MINIO_BUCKET,
        chunk_info['storeFilename'],
        bit_packed_element_size * chunk_range_start,
        chunk_bytes)

    chunk_data = binary_unpack_filters(chunk_stream.stream(bit_packed_element_size), chunk_bytes, encoding_size)

    return chunk_data, chunk_length
