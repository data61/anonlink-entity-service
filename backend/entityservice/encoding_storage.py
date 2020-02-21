import ijson
from entityservice.serialization import deserialize_bytes, binary_format


def stream_json_clksnblocks(f):
    """

    :param f: JSON file containing clksnblocks data.
    :return: Generator of (entity_id, base64 encoding, list of blocks)
    """
    # At some point the user may supply the entity id. For now we use the order of uploaded encodings.
    for i, obj in enumerate(ijson.items(f, 'clksnblocks.item')):
        b64_encoding, *blocks = obj
        yield i, deserialize_bytes(b64_encoding), blocks


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

    for i, encoding_data, blocks in stream_json_clksnblocks(f):
        if encoding_size is None:
            encoding_size = len(encoding_data)
            bit_packing_struct = binary_format(encoding_size)
        binary_packed_encoding = bit_packing_struct.pack(i, encoding_data)
        for block in blocks:
            encodings_by_block.setdefault(block, []).append(binary_packed_encoding)

    return encodings_by_block, encoding_size

