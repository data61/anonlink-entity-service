from pathlib import Path
import io

from entityservice.encoding_storage import convert_encodings_from_json_to_binary
from entityservice.tests.util import serialize_bytes


class TestEncodingStorage:
    def test_convert_encodings_from_json_to_binary_simple(self):
        filename = Path(__file__).parent / 'testdata' / 'test_encoding.json'
        with open(filename) as f:
            binary_dict, encoding_length = convert_encodings_from_json_to_binary(f)
            assert encoding_length == 128
            assert len(binary_dict) == 2
            assert len(binary_dict['1']) == 3
            assert len(binary_dict['2']) == 2
            assert len(set(binary_dict['1']).intersection(binary_dict['2'])) == 1

    def test_convert_encodings_from_json_to_binary_empty(self):
        empty = io.BytesIO(b'''{
            "clksnblocks": []
         }''')

        binary_dict, encoding_length = convert_encodings_from_json_to_binary(empty)
        assert binary_dict == {}
        assert encoding_length is None

    def test_convert_encodings_from_json_to_binary_short(self):
        d = serialize_bytes(b'abcdabcd')
        json_data = io.BytesIO(b'{' + f'''"clksnblocks": [["{d}", "02"]]'''.encode() + b'}')
        binary_dict, encoding_length = convert_encodings_from_json_to_binary(json_data)
        assert encoding_length == 8
        assert "02" in binary_dict
        assert len(binary_dict["02"]) == 1
        assert len(binary_dict["02"][0]) == 8 + 4   # size of encoding + id

