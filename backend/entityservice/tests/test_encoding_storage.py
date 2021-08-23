import time

from pathlib import Path
import io

import pytest

from entityservice.encoding_storage import hash_block_name, stream_json_clksnblocks
from entityservice.tests.util import serialize_bytes


class TestEncodingStorage:
    def test_convert_encodings_from_json_to_binary_simple(self):
        filename = Path(__file__).parent / 'testdata' / 'test_encoding.json'
        with open(filename, 'rb') as f:
            # stream_json_clksnblocks produces a generator of (entity_id, base64 encoding, list of blocks)
            encoding_ids, encodings, blocks = list(zip(*stream_json_clksnblocks(f)))

            assert len(encoding_ids) == 4
            assert len(encodings) == 4
            first_blocks = list(blocks[0])
            assert len(first_blocks) == 1
            assert first_blocks[0] == hash_block_name('1')

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
        assert hash_block_name("02") in blocks[0]

    def test_convert_encodings_from_json_to_binary_large_block_name(self):
        d = serialize_bytes(b'abcdabcd')
        large_block_name = 'b10ck' * 64
        json_data = io.BytesIO(b'{' + f'''"clknblocks": [["{d}", "{large_block_name}"]]'''.encode() + b'}')
        encoding_ids, encodings, blocks = list(zip(*stream_json_clksnblocks(json_data)))

        assert len(hash_block_name(large_block_name)) <= 64
        assert len(encodings[0]) == 8
        assert hash_block_name(large_block_name) in blocks[0]

    def test_hash_block_names_speed(self):
        timeout = 10
        input_strings = [str(i) for i in range(1_000_000)]
        start_time = time.time()

        for i, input_str in enumerate(input_strings):
            hash_block_name(input_str)
            if i % 10_000 == 0:
                assert time.time() <= (start_time + timeout)
