from bitarray import bitarray
import base64
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
    ba = bitarray()
    data_as_bytes = base64.decodebytes(bytes_data.encode())
    ba.frombytes(data_as_bytes)
    return ba


def serialize_bitarray(ba):
    """ Serialize a bitarray (bloomfilter)

    """
    return base64.encodebytes(ba.tobytes()).decode('utf8')



def serialize_filters(filters):
    return [
        serialize_bitarray(f[0]) for f in filters
    ]


def deserialize_filters(filters):
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
