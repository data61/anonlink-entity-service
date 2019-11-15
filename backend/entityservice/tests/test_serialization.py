import io
import unittest
import random

import json
from array import array

import anonlink

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

    def test_generate_scores_produces_json(self):
        sims_iter = (
            array('d', [0.1, 0.01, 1.0]),
            (array('I', [0, 0, 0]), array('I', [1, 1, 1])),
            (array('I', [1, 2, 5]), array('I', [2, 2, 5]))
        )

        buffer = io.BytesIO()
        anonlink.serialization.dump_candidate_pairs(sims_iter, buffer)
        buffer.seek(0)
        json_iterator = generate_scores(buffer)

        # Consume the whole iterator and ensure it is valid json
        json_str = ''.join(json_iterator)
        json_obj = json.loads(json_str)
        self.assertIn('similarity_scores', json_obj)
        assert len(json_obj["similarity_scores"]) == 3
        for pair_and_score in json_obj["similarity_scores"]:
            self.assertEqual(len(pair_and_score), 3)
            a, b, score = pair_and_score
            self.assertEqual(len(a), 2)
            self.assertEqual(len(b), 2)

    def test_sims_to_json_empty(self):
        sims_iter = (
            array('d', []),
            (array('I', []), array('I', [])),
            (array('I', []), array('I', []))
        )

        buffer = io.BytesIO()
        anonlink.serialization.dump_candidate_pairs(sims_iter, buffer)
        buffer.seek(0)
        json_iterator = generate_scores(buffer)

        # Consume the whole iterator and ensure it is valid json
        json_str = ''.join(json_iterator)
        json_obj = json.loads(json_str)
        self.assertIn('similarity_scores', json_obj)
        assert len(json_obj["similarity_scores"]) == 0


if __name__ == "__main__":
    unittest.main()
