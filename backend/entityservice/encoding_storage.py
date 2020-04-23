import math
from itertools import zip_longest
from typing import Iterator, List, Tuple

import ijson
import opentracing
from flask import g
from structlog import get_logger

from entityservice import database as db
from entityservice.database import insert_encodings_into_blocks, get_encodingblock_ids, \
    get_chunk_of_encodings, DBConn
from entityservice.serialization import deserialize_bytes, binary_format, binary_unpack_filters
#from entityservice.tasks import check_for_executable_runs
from entityservice.tracing import serialize_span
from entityservice.utils import clks_uploaded_to_project, fmt_bytes

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
    :return: Generator of (entity_id, base64 encoding, list of blocks)
    """
    # At some point the user may supply the entity id. For now we use the order of uploaded encodings.
    for i, obj in enumerate(ijson.items(f, 'clknblocks.item')):
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


def get_encoding_chunk(conn, chunk_info, encoding_size=128):
    chunk_range_start, chunk_range_stop = chunk_info['range']
    dataprovider_id = chunk_info['dataproviderId']
    block_id = chunk_info['block_id']
    limit = chunk_range_stop - chunk_range_start
    encoding_ids = get_encodingblock_ids(conn, dataprovider_id, block_id, chunk_range_start, limit)
    encoding_iter = get_chunk_of_encodings(conn, dataprovider_id, encoding_ids, stored_binary_size=(encoding_size+4))
    chunk_data = binary_unpack_filters(encoding_iter, encoding_size=encoding_size)
    return chunk_data, len(chunk_data)


def upload_clk_data_binary(project_id, dp_id, encoding_iter, receipt_token, count, size=128):
    """
    Save the user provided binary-packed CLK data.

    """
    filename = None
    # Set the state to 'pending' in the uploads table
    with DBConn() as conn:
        db.insert_encoding_metadata(conn, filename, dp_id, receipt_token, encoding_count=count, block_count=1)
        db.update_encoding_metadata_set_encoding_size(conn, dp_id, size)
    logger.info(f"Storing supplied binary clks of individual size {size} in file: {filename}")

    num_bytes = binary_format(size).size * count

    logger.debug("Directly storing binary file with index, base64 encoded CLK, popcount")

    # Upload to database
    logger.info(f"Uploading {count} binary encodings to database. Total size: {fmt_bytes(num_bytes)}")
    parent_span = g.flask_tracer.get_span()

    with DBConn() as conn:
        with opentracing.tracer.start_span('create-default-block-in-db', child_of=parent_span):
            db.insert_blocking_metadata(conn, dp_id, {DEFAULT_BLOCK_ID: count})

        with opentracing.tracer.start_span('upload-encodings-to-db', child_of=parent_span):
            store_encodings_in_db(conn, dp_id, encoding_iter, size)

        with opentracing.tracer.start_span('update-encoding-metadata', child_of=parent_span):
            db.update_encoding_metadata(conn, filename, dp_id, 'ready')

    # # Now work out if all parties have added their data
    # if clks_uploaded_to_project(project_id):
    #     logger.info("All parties data present. Scheduling any queued runs")
    #     check_for_executable_runs.delay(project_id, serialize_span(parent_span))


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

