from bitarray import bitarray
import base64
import struct

from entityservice.settings import Config as config
from entityservice.utils import chunks
import concurrent.futures
import phe.util
from phe import paillier


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


def load_public_key(pk):
    MALFORMED_ERROR = "Malformed Public Key"
    for attr in {'key_ops', 'kty', 'alg'}:
        assert attr in pk, MALFORMED_ERROR
    assert pk['kty'] == "DAJ", "Unsupported key type"
    assert pk['alg'] == "PAI-GN1", "Unsupported algorithm type"
    assert 'n' in pk, MALFORMED_ERROR
    n = phe.util.base64_to_int(pk['n'])
    return paillier.PaillierPublicKey(n)


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


def check_public_key(pk):
    """
    Check we can unmarshal the public key, and that it has sufficient length.
    """
    publickey = load_public_key(pk)
    return publickey.max_int >= 2 ** config.ENCRYPTION_MIN_KEY_LENGTH