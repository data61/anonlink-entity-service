import io
import unittest
import random
from bitarray import bitarray
from serialization import deserialize_bitarray, generate_scores
from .util import serialize_bitarray


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
        csv_byte_stream = io.BytesIO("1,2,3\n1,2,3\n,5,5,5".encode("utf-8"))
        csv_text_stream = io.TextIOWrapper(csv_byte_stream, encoding="utf-8")
        response = generate_scores(csv_text_stream)


if __name__ == "__main__":
    unittest.main()
