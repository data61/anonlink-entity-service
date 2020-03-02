import math
from itertools import zip_longest
from typing import Iterator, List, Tuple

import ijson

from entityservice.database import insert_encodings_into_blocks
from entityservice.serialization import deserialize_bytes, binary_format


def stream_json_clksnblocks(f):
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

    :param f: JSON file containing clksnblocks data.
    :return: Generator of (entity_id, base64 encoding, list of blocks)
    """
    # At some point the user may supply the entity id. For now we use the order of uploaded encodings.
    for i, obj in enumerate(ijson.items(f, 'clksnblocks.item')):
        b64_encoding, *blocks = obj
        yield i, deserialize_bytes(b64_encoding), blocks


def convert_encodings_from_base64_to_binary(encodings: Iterator[Tuple[str, str, List[str]]]):
    """
    :param encodings: Iterable object containing tuples of  (entity_id, base64 encoding, list of blocks)
    :return: a tuple comprising:
         (entity_id, binary encoding, list of blocks)
    """
    # Peek at the first element to extract the encoding size
    i, encoding_data, blocks = next(encodings)
    encoding_size = len(encoding_data)
    bit_packing_struct = binary_format(encoding_size)

    def generator(first_i, first_encoding_data, first_blocks):
        binary_packed_encoding = bit_packing_struct.pack(first_i, first_encoding_data)
        yield first_i, binary_packed_encoding, first_blocks
        for i, encoding_data, blocks in encodings:
            binary_packed_encoding = bit_packing_struct.pack(i, encoding_data)
            yield i, binary_packed_encoding, blocks

    return encoding_size, generator(i, encoding_data, blocks)

def _grouper(iterable, n, fillvalue=None):
    "Collect data into fixed-length chunks or blocks"
    # grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx"
    args = [iter(iterable)] * n
    return zip_longest(*args, fillvalue=fillvalue)


def _transpose(group):
    """
    Given a list of 3-tuples from _grouper, return 3 lists.
    Also filter out possible None values from _grouper
    """
    a, b, c = [], [], []
    for g in group:
        # g can be None
        if g is not None:

            x, y, z = g
            #if x is not None and y is not None and z is not None:
            a.append(x)
            b.append(y)
            c.append(z)
    return a, b, c


def store_encodings_in_db(conn, dp_id, encodings: Iterator[Tuple[str, bytes, List[str]]], encoding_size: int=128):
    """
    Group encodings + blocks into database transactions and execute.
    """

    for group in _grouper(encodings, n=_estimate_group_size(encoding_size)):
        encoding_ids, encodings, blocks = _transpose(group)
        assert len(blocks) == len(encodings)
        assert len(encoding_ids) == len(encodings)
        insert_encodings_into_blocks(conn, dp_id, block_ids=blocks, encoding_ids=encoding_ids, encodings=encodings)


def _estimate_group_size(encoding_size):
    """
    Given an encoding size (e.g. 128 B), estimate the number of encodings that will likely
    be under 100MiB in data including blocks. Note this is hopefully very conservative
    in estimating the average number of blocks each record is in.
    """
    network_transaction_size = 104857600  # 100MiB
    blocks_per_record_estimate = 50
    return math.ceil(network_transaction_size / ((blocks_per_record_estimate * 64) + (encoding_size + 4)))


def convert_encodings_from_json_to_binary(f):
    """
    Temp helper function

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

