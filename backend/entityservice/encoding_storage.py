import ijson
from entityservice.serialization import deserialize_bytes, binary_format


def convert_encodings_from_json_to_binary(f):
    """
    The provided file will be contain encodings and blocking information with
    the following structure:

    {
        "clksnblocks": [
            ["BASE64 ENCODED ENCODING 1", blockid1, blockid2, ...],
            ["BASE64 ENCODED ENCODING 2", blockid1, ...],
            ...
        ]
    }

    .. Note::
        Entities belonging to no blocks get ignored.


    TODO:
        Currently we do everything in memory.
        Eventually we might want to instead stream through the input (perhaps twice).

    :param f: File-like object containing `clksnblocks` json.
    :return: a tuple comprising:
        - dict mapping blocks to lists of bytes (each encoding in our internal encoding file format)
        - the size of the first encoding in bytes (excluding entity ID info)
    """
    # Each block index contains a set of base64 encodings.
    encodings_by_block = {}

    # Default which is ignored but makes IDE/typechecker happier
    bit_packing_struct = binary_format(128)
    encoding_size = None

    encodings_and_block_iter = ijson.items(f, 'clksnblocks.item')
    # At some point the user may supply the entity id. For now we use the order of uploaded encodings.
    for i, obj in enumerate(encodings_and_block_iter):
        b64_encoding, *blocks = obj
        deserialized_encoding_data = deserialize_bytes(b64_encoding)
        if i == 0:
            encoding_size = len(deserialized_encoding_data)
            bit_packing_struct = binary_format(encoding_size)
        encoding = bit_packing_struct.pack(i, deserialized_encoding_data)
        for block in blocks:
            encodings_by_block.setdefault(block, []).append(encoding)

    return encodings_by_block, encoding_size

