import io
import json
import random
import unittest
from array import array

import anonlink

from entityservice.serialization import deserialize_bytes, generate_scores, binary_pack_filters, \
    binary_unpack_filters, binary_unpack_one, binary_format
from entityservice.tests.util import serialize_bytes, generate_bytes


class SerializationTest(unittest.TestCase):

    def test_bitarray(self):
        ba = b'\xec\xddUUUU^f'

        serialized_bitarray1 = serialize_bytes(ba)

        banew = deserialize_bytes(serialized_bitarray1)

        self.assertEqual(banew, ba)

    def test_random_bytes(self):
        rb = generate_bytes(2048//8)
        srb = serialize_bytes(rb)
        dsrb = deserialize_bytes(srb)
        self.assertEqual(dsrb, rb)

    def test_generate_scores_produces_json(self):
        sims_iter = (
            array('d', [0.1, 0.01, 1.0]),
            (array('I', [0, 0, 0]), array('I', [1, 1, 1])),
            (array('I', [1, 2, 5]), array('I', [2, 2, 5]))
        )

        json_obj = self._serialize_and_load_scores(sims_iter)
        assert len(json_obj["similarity_scores"]) == 3
        for pair_and_score in json_obj["similarity_scores"]:
            self.assertEqual(len(pair_and_score), 3)
            a, b, score = pair_and_score
            self.assertEqual(len(a), 2)
            self.assertEqual(len(b), 2)

    def _serialize_and_load_scores(self, sims_iter):
        buffer = io.BytesIO()
        anonlink.serialization.dump_candidate_pairs(sims_iter, buffer)
        buffer.seek(0)
        json_iterator = generate_scores(buffer)
        # Consume the whole iterator and ensure it is valid json
        json_str = ''.join(json_iterator)
        json_obj = json.loads(json_str)
        self.assertIn('similarity_scores', json_obj)
        return json_obj

    def test_sims_to_json_empty(self):
        sims_iter = (
            array('d', []),
            (array('I', []), array('I', [])),
            (array('I', []), array('I', []))
        )

        json_obj = self._serialize_and_load_scores(sims_iter)
        assert len(json_obj["similarity_scores"]) == 0

    def test_binary_pack_filters(self):
        encoding_size = 128
        filters = [(random.randint(0, 2 ** 32 - 1), generate_bytes(encoding_size)) for _ in range(10)]
        packed_filters = binary_pack_filters(filters, encoding_size)
        bin_format = binary_format(encoding_size)
        for filter, packed_filter in zip(filters, packed_filters):
            assert len(packed_filter) == encoding_size + 4
            unpacked = binary_unpack_one(packed_filter, bin_format)
            assert filter == unpacked

    def test_binary_unpack_filters(self):
        encoding_size = 128
        filters = [(random.randint(0, 2 ** 32 - 1), generate_bytes(encoding_size)) for _ in range(10)]
        laundered_filters = binary_unpack_filters(binary_pack_filters(filters, encoding_size),
                                                  encoding_size=encoding_size)
        assert filters == laundered_filters


if __name__ == "__main__":
    unittest.main()
