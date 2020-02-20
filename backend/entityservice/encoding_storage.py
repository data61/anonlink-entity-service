

import ijson
from pathlib import Path
from entityservice.serialization import binary_pack_filters, deserialize_bytes, binary_format


def convert_encodings_from_json_to_binary(f, encoding_size=128):
    """
    The provided file will be in a JSON array with the following structure:

    {
        "clksnblocks": [
            ["BASE64 ENCODED ENCODING 1", blockid1, blockid2, ...],
            ["BASE64 ENCODED ENCODING 2", blockid1, ...],
            ...
        ]
    }

    The output data will be a binary file of just the encodings for each block.

    Initially we do everything in memory.

    TODO:
        Eventually we might want to instead stream through the input twice, first counting the
        number of encodings in each block, and on the second pass streaming the encodings directly
        into their pre-allocated per-block output files.

    :param f: File like object containing `clksnblocks` json.
    :param encoding_size: the size of one encoding in bytes, excluding entity ID info
    :return: a dict mapping blocks to lists of bytes (each encoding in our internal encoding file format)
    """
    # Each block index contains a set of base64 encodings.
    encodings_by_block = {}

    bit_packing_struct = binary_format(encoding_size)

    encodings_and_block_iter = ijson.items(f, 'clksnblocks.item')
    # At some point the user may supply the entity id. For now we use the order of uploaded encodings.
    for i, obj in enumerate(encodings_and_block_iter):
        b64_encoding, *blocks = obj
        deserialized_encoding_data = deserialize_bytes(b64_encoding)
        encoding = bit_packing_struct.pack(i, deserialized_encoding_data)
        for block in blocks:
            encodings_by_block.setdefault(block, []).append(encoding)

    return encodings_by_block


if __name__ == '__main__':
    filename = Path(__file__).parent / 'test_encoding.json'
    with open(filename) as f:
        print(convert_encodings_from_json_to_binary(f))
