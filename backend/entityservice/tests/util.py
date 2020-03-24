import base64
import random
import tempfile
from contextlib import contextmanager


@contextmanager
def temp_file_containing(data):
    with tempfile.NamedTemporaryFile('wb') as fp:
        fp.write(data)
        fp.seek(0)
        yield fp


def serialize_bytes(hash_bytes):
    """ Serialize bloomfilter bytes

    """
    return base64.b64encode(hash_bytes).decode()


def generate_bytes(length):
    return random.getrandbits(length * 8).to_bytes(length, 'big')

