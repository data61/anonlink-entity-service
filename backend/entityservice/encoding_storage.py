from hashlib import blake2b

import math
from collections import defaultdict
from itertools import zip_longest
from typing import Iterator, List, Tuple, Iterable

import ijson
import opentracing
from flask import g
from structlog import get_logger

from entityservice import database as db
from entityservice.database import insert_encodings_into_blocks, get_encodingblock_ids, \
    get_chunk_of_encodings, get_encodings_of_multiple_blocks, DBConn
from entityservice.serialization import deserialize_bytes, binary_format, binary_unpack_filters, binary_unpack_one
from entityservice.utils import fmt_bytes

logger = get_logger()

DEFAULT_BLOCK_ID = '1'


def stream_json_clksnblocks(f):
    """
    The provided file will be contain encodings and blocking information with
    the following structure:

    {
        "clknblocks": [
            ["BASE64 ENCODED ENCODING 1", blockid1, blockid2, ...],
            ["BASE64 ENCODED ENCODING 2", blockid1, ...],
            ...
        ]
    }

    :param f: JSON file containing clksnblocks data.
    :return: Generator of (entity_id, base64 encoding, iterable of hashed block names)
    """
    # At some point the user may supply the entity id. For now we use the order of uploaded encodings.
    for i, obj in enumerate(ijson.items(f, 'clknblocks.item')):
        b64_encoding, *blocks = obj
        yield i, deserialize_bytes(b64_encoding), map(hash_block_name, blocks)


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
    "Collect data into fixed-length chunks or blocks from an iterable"
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
        assert len(blocks) == len(encodings), "Block length and encoding length don't match"
        assert len(encoding_ids) == len(encodings), "Length of encoding ids and encodings don't match"
        logger.debug("Processing group", num_encoding_ids=len(encoding_ids), num_blocks=len(blocks))
        insert_encodings_into_blocks(conn, dp_id, block_names=blocks, entity_ids=encoding_ids, encodings=encodings)


def _estimate_group_size(encoding_size):
    """
    Given an encoding size (e.g. 128 B), estimate the number of encodings that will likely
    be under 100MiB in data including blocks. Note this is hopefully very conservative
    in estimating the average number of blocks each record is in.
    """
    network_transaction_size = 104857600  # 100MiB
    blocks_per_record_estimate = 50
    return math.ceil(network_transaction_size / ((blocks_per_record_estimate * 64) + (encoding_size + 4)))


def get_encoding_chunk(conn, chunk_info, encoding_size=128):
    chunk_range_start, chunk_range_stop = chunk_info['range']
    dataprovider_id = chunk_info['dataproviderId']
    block_id = chunk_info['block_id']
    limit = chunk_range_stop - chunk_range_start
    encoding_ids = get_encodingblock_ids(conn, dataprovider_id, block_id, chunk_range_start, limit)
    encoding_iter = get_chunk_of_encodings(conn, dataprovider_id, encoding_ids, stored_binary_size=(encoding_size+4))
    chunk_data = binary_unpack_filters(encoding_iter, encoding_size=encoding_size)
    return chunk_data, len(chunk_data)


def get_encoding_chunks(conn, package, encoding_size=128):
    """enrich the chunks in the package with the encodings and entity_ids"""
    chunks_per_dp = defaultdict(list)
    for chunk_info_1, chunk_info_2 in package:
        chunks_per_dp[chunk_info_1['dataproviderId']].append(chunk_info_1)
        chunks_per_dp[chunk_info_2['dataproviderId']].append(chunk_info_2)

    encodings_with_ids = {}
    for dp_id in chunks_per_dp:
        #get all encodings for that dp, save in dict with blockID as key.
        chunks = sorted(chunks_per_dp[dp_id], key=lambda chunk: chunk['block_id'])
        block_ids = [chunk['block_id'] for chunk in chunks]
        values = get_encodings_of_multiple_blocks(conn, dp_id, block_ids)
        i = 0

        bit_packing_struct = binary_format(encoding_size)

        def block_values_iter(values):
            block_id, entity_id, encoding = next(values)
            entity_ids = [entity_id]
            encodings = [binary_unpack_one(encoding, bit_packing_struct)[1]]
            while True:
                try:
                    new_id, n_entity_id, n_encoding = next(values)
                    if new_id == block_id:
                        entity_ids.append(n_entity_id)
                        encodings.append(binary_unpack_one(n_encoding, bit_packing_struct)[1])
                    else:
                        yield block_id, entity_ids, encodings
                        block_id = new_id
                        entity_ids = [n_entity_id]
                        encodings = [binary_unpack_one(n_encoding, bit_packing_struct)[1]]
                except StopIteration:
                    yield block_id, entity_ids, encodings
                    break

        for block_id, entity_ids, encodings in block_values_iter(values):
            encodings_with_ids[(dp_id, block_id)] = (entity_ids, encodings)

    for chunk_info_1, chunk_info_2 in package:
        entity_ids, encodings = encodings_with_ids[(chunk_info_1['dataproviderId'], chunk_info_1['block_id'])]
        chunk_info_1['encodings'] = encodings
        chunk_info_1['entity_ids'] = entity_ids
        entity_ids, encodings = encodings_with_ids[(chunk_info_2['dataproviderId'], chunk_info_2['block_id'])]
        chunk_info_2['encodings'] = encodings
        chunk_info_2['entity_ids'] = entity_ids

    return package


def upload_clk_data_binary(project_id, dp_id, encoding_iter, receipt_token, count, size=128, parent_span=None):
    """
    Save the user provided binary-packed CLK data.

    """
    filename = None
    # Set the state to 'pending' in the uploads table
    with DBConn() as conn:
        db.insert_encoding_metadata(conn, filename, dp_id, receipt_token, encoding_count=count, block_count=1)
        db.update_encoding_metadata_set_encoding_size(conn, dp_id, size)
    num_bytes = binary_format(size).size * count

    logger.debug("Directly storing binary file with index, base64 encoded CLK, popcount")

    # Upload to database
    logger.info(f"Uploading {count} binary encodings to database. Total size: {fmt_bytes(num_bytes)}")

    with DBConn() as conn:
        db.update_encoding_metadata_set_encoding_size(conn, dp_id, size)

        with opentracing.tracer.start_span('create-default-block-in-db', child_of=parent_span):
            db.insert_blocking_metadata(conn, dp_id, {DEFAULT_BLOCK_ID: count})

        with opentracing.tracer.start_span('upload-encodings-to-db', child_of=parent_span):
            store_encodings_in_db(conn, dp_id, encoding_iter, size)

        with opentracing.tracer.start_span('update-encoding-metadata', child_of=parent_span):
            db.update_encoding_metadata(conn, filename, dp_id, 'ready')


def include_encoding_id_in_binary_stream(stream, size, count):
    """
    Inject an encoding_id and default block into a binary stream of encodings.
    """

    binary_formatter = binary_format(size)

    def encoding_iterator(filter_stream):
        # Assumes encoding id and block info not provided (yet)
        for entity_id in range(count):
            yield str(entity_id), binary_formatter.pack(entity_id, filter_stream.read(size)), [DEFAULT_BLOCK_ID]

    return encoding_iterator(stream)


def include_encoding_id_in_json_stream(stream, size, count):
    """
    Inject an encoding_id and default block into a ijson stream of encodings.
    :param stream: ijson object
    :param count: integer
    :return: generator
    """
    binary_formatter = binary_format(size)

    def encoding_iterator(filter_stream):
        # Assumes encoding id and block info not provided (yet)
        for entity_id, encoding in zip(range(count), filter_stream):
            yield str(entity_id), binary_formatter.pack(entity_id, deserialize_bytes(encoding)), [DEFAULT_BLOCK_ID]

    return encoding_iterator(stream)


def hash_block_name(provided_block_name):
    block_hmac_instance = blake2b(digest_size=32)
    block_hmac_instance.update(str(provided_block_name).encode())
    provided_block_name = block_hmac_instance.hexdigest()
    return provided_block_name
