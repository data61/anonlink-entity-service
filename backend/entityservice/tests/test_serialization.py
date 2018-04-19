import io
import unittest
import random

import json
from bitarray import bitarray
from entityservice.serialization import deserialize_bitarray, generate_scores
from entityservice.tests.util import serialize_bitarray


def random_bitarray(l=1024):
    return bitarray(
        ''.join('1' if random.random() > 0.5 else '0' for _ in range(l))
    )


class SerializationTest(unittest.TestCase):

    def test_bitarray(self):
        ba = bitarray('1110110011011101010101010101010101010101010101010101111001100110')

        serialized_bitarray1 = serialize_bitarray(ba)

        banew = deserialize_bitarray(serialized_bitarray1)

        self.assertEqual(banew, ba)

    def test_random_bitarray(self):
        ba = random_bitarray(2048)
        sba = serialize_bitarray(ba)
        dsba = deserialize_bitarray(sba)
        self.assertEqual(dsba, ba)


    def test_csv_to_json(self):
        csv_byte_stream = io.BytesIO("1,2,0.1\n1,2,0.01\n5,5,1.0".encode("utf-8"))
        csv_text_stream = io.TextIOWrapper(csv_byte_stream, encoding="utf-8")
        json_iterator = generate_scores(csv_text_stream)

        # Consume the whole iterator and ensure it is valid json
        json_str = ''.join(json_iterator)
        json_obj = json.loads(json_str)
        self.assertIn('similarity_scores', json_obj)
        for score in json_obj["similarity_scores"]:
            self.assertEqual(len(score), 3)

    def test_csv_to_json_empty(self):
        csv_byte_stream = io.BytesIO("".encode("utf-8"))
        csv_text_stream = io.TextIOWrapper(csv_byte_stream, encoding="utf-8")
        json_iterator = generate_scores(csv_text_stream)

        # Consume the whole iterator and ensure it is valid json
        json_str = ''.join(json_iterator)
        json_obj = json.loads(json_str)
        self.assertIn('similarity_scores', json_obj)
        for score in json_obj["similarity_scores"]:
            self.assertEqual(len(score), 3)


if __name__ == "__main__":
    unittest.main()
