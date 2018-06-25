import io
from entityservice.utils import chain_streams


def test_chaining_streams():

    f1 = io.BytesIO(b'1abc')
    f2 = io.BytesIO(b'2abc')
    f3 = io.BytesIO(b'3abc')
    f4 = io.BufferedReader(io.BytesIO(b'4abc'))

    s = chain_streams((f for f in [f1, f2, f3, f4]))

    data = s.read()

    assert len(data) == 16
