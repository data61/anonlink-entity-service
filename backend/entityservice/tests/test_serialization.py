import io
import unittest
import random

import json
from entityservice.serialization import deserialize_bytes, generate_scores
from entityservice.tests.util import serialize_bytes


def random_bytes(l=1024):
    return random.getrandbits(l).to_bytes(l // 8, 'big')


class SerializationTest(unittest.TestCase):

    def test_bitarray(self):
        ba = b'\xec\xddUUUU^f'

        serialized_bitarray1 = serialize_bytes(ba)

        banew = deserialize_bytes(serialized_bitarray1)

        self.assertEqual(banew, ba)

    def test_random_bytes(self):
        rb = random_bytes(2048)
        srb = serialize_bytes(rb)
        dsrb = deserialize_bytes(srb)
        self.assertEqual(dsrb, rb)


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
