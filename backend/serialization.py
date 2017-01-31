from bitarray import bitarray
import base64
import struct
import phe.util
from phe import paillier

from phe.util import int_to_base64, base64_to_int

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


def serialize_bitarray(ba):
    """ Serialize a bitarray (bloomfilter)

    """
    return base64.encodebytes(ba.tobytes()).decode('utf8')

bit_packing_fmt = "!1I128p1H"
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

    ba = bitarray(endian="big")
    ba.frombytes(clk_bytes)
    return ba, index, count


def binary_unpack_filters(streamable_data):
    filters = []
    for raw_bytes in streamable_data.stream(bit_packed_element_size):
        filters.append(binary_unpack_one(raw_bytes))

    return filters


def serialize_filters(filters):
    """Serialize filters as clients are required to."""
    return [
        serialize_bitarray(f[0]) for f in filters
    ]


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


def load_public_key(pk):
    MALFORMED_ERROR = "Malformed Public Key"
    for attr in {'key_ops', 'kty', 'alg'}:
        assert attr in pk, MALFORMED_ERROR
    assert pk['kty'] == "DAJ", "Unsupported key type"
    assert pk['alg'] == "PAI-GN1", "Unsupported algorithm type"
    assert 'n' in pk, MALFORMED_ERROR
    n = phe.util.base64_to_int(pk['n'])
    return paillier.PaillierPublicKey(n+1, n)
