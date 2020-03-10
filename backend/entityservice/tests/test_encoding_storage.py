from pathlib import Path
import io

import pytest

from entityservice.encoding_storage import stream_json_clksnblocks
from entityservice.tests.util import serialize_bytes


class TestEncodingStorage:
    def test_convert_encodings_from_json_to_binary_simple(self):
        filename = Path(__file__).parent / 'testdata' / 'test_encoding.json'
        with open(filename, 'rb') as f:
            # stream_json_clksnblocks produces a generator of (entity_id, base64 encoding, list of blocks)
            encoding_ids, encodings, blocks = list(zip(*stream_json_clksnblocks(f)))
            assert len(encoding_ids) == 4
            assert len(encodings) == 4
            assert len(blocks[0]) == 1
            assert blocks[0][0] == '1'

    def test_convert_encodings_from_json_to_binary_empty(self):
        empty = io.BytesIO(b'''{
            "clknblocks": []
         }''')

        with pytest.raises(StopIteration):
            next(stream_json_clksnblocks(empty))

    def test_convert_encodings_from_json_to_binary_short(self):
        d = serialize_bytes(b'abcdabcd')
        json_data = io.BytesIO(b'{' + f'''"clknblocks": [["{d}", "02"]]'''.encode() + b'}')
        encoding_ids, encodings, blocks = list(zip(*stream_json_clksnblocks(json_data)))

        assert len(encodings[0]) == 8
        assert "02" in blocks[0]

