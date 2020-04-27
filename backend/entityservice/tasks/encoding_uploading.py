import json

from entityservice.database import *
from entityservice.encoding_storage import stream_json_clksnblocks, convert_encodings_from_base64_to_binary, \
    store_encodings_in_db, upload_clk_data_binary, include_encoding_id_in_binary_stream
from entityservice.error_checking import check_dataproviders_encoding, handle_invalid_encoding_data, \
    InvalidEncodingError
from entityservice.object_store import connect_to_object_store, stat_and_stream_object, parse_minio_credentials
from entityservice.serialization import binary_format
from entityservice.settings import Config
from entityservice.async_worker import celery, logger
from entityservice.tasks.base_task import TracedTask
from entityservice.tasks.pre_run_check import check_for_executable_runs
from entityservice.utils import fmt_bytes, clks_uploaded_to_project

logger = get_logger()


@celery.task(base=TracedTask, ignore_result=True, args_as_tags=('project_id', 'dp_id'))
def pull_external_data(project_id, dp_id,
                                      encoding_object_info, encoding_credentials,
                                      blocks_object_info, blocks_credentials,
                                      receipt_token, parent_span=None):
    """
    Load encoding and blocking data from object store.

    - pull blocking map into memory, create blocks in db
    - stream encodings into DB and add encoding + blocks from in memory dict.

    """
    log = logger.bind(pid=project_id, dp_id=dp_id)
    with DBConn() as conn:
        if not check_project_exists(conn, project_id):
            log.info("Project deleted, stopping immediately")
            return

        mc = connect_to_object_store(parse_minio_credentials(blocks_credentials))

    log.debug("Pulling blocking information from object store")
    response = mc.get_object(bucket_name=blocks_object_info['bucket'], object_name=blocks_object_info['path'])
    encoding_to_block_map = json.load(response)

    log.debug("Counting the blocks")
    block_sizes = {}
    for encoding_id in encoding_to_block_map:
        _blocks = encoding_to_block_map[encoding_id]
        for block_id in _blocks:
            block_id = str(block_id)
            block_sizes[block_id] = block_sizes.setdefault(block_id, 0) + 1

    block_count = len(block_sizes)
    log.debug(f"Processing {block_count} blocks")

    # stream the encodings
    bucket_name = encoding_object_info['bucket']
    object_name = encoding_object_info['path']

    stat, encodings_stream = stat_and_stream_object(bucket_name, object_name, parse_minio_credentials(encoding_credentials))
    count = int(stat.metadata['X-Amz-Meta-Hash-Count'])
    size = int(stat.metadata['X-Amz-Meta-Hash-Size'])
    log.debug(f"Processing {count} encodings")
    assert count == len(encoding_to_block_map), f"Expected {count} encodings in blocks. Got {len(encoding_to_block_map)}"

    with DBConn() as conn:
        with opentracing.tracer.start_span('update-metadata-db', child_of=parent_span):
            update_encoding_metadata_set_encoding_size(conn, dp_id, size)
            insert_encoding_metadata(conn, None, dp_id, receipt_token, encoding_count=count, block_count=block_count)
        with opentracing.tracer.start_span('create-block-entries-in-db', child_of=parent_span):
            log.debug("Adding blocks to db")
            insert_blocking_metadata(conn, dp_id, block_sizes)

        def encoding_iterator(encoding_stream):
            binary_formatter = binary_format(size)
            for encoding_id in range(count):
                yield (
                    str(encoding_id),
                    binary_formatter.pack(encoding_id, encoding_stream.read(size)),
                    encoding_to_block_map[str(encoding_id)]
                    )

        with opentracing.tracer.start_span('upload-encodings-to-db', child_of=parent_span):
            log.debug("Adding encodings and associated blocks to db")
            try:
                store_encodings_in_db(conn, dp_id, encoding_iterator(encodings_stream), size)
            except Exception as e:
                update_dataprovider_uploaded_state(conn, project_id, dp_id, 'error')
                log.warning(e)

        with opentracing.tracer.start_span('update-encoding-metadata', child_of=parent_span):
            update_encoding_metadata(conn, None, dp_id, 'ready')
            update_blocks_state(conn, dp_id, block_sizes.keys(), 'ready')


@celery.task(base=TracedTask, ignore_result=True, args_as_tags=('project_id', 'dp_id'))
def pull_external_data_encodings_only(project_id, dp_id, object_info, credentials, receipt_token, parent_span=None):
    """

    """
    log = logger.bind(pid=project_id, dp_id=dp_id)

    with DBConn() as conn:
        if not check_project_exists(conn, project_id):
            log.info("Project deleted, stopping immediately")
            return

        bucket_name = object_info['bucket']
        object_name = object_info['path']

    log.info("Pulling encoding data from an object store")
    mc_credentials = parse_minio_credentials(credentials)
    stat, stream = stat_and_stream_object(bucket_name, object_name, mc_credentials)

    count = int(stat.metadata['X-Amz-Meta-Hash-Count'])
    size = int(stat.metadata['X-Amz-Meta-Hash-Size'])
    converted_stream = include_encoding_id_in_binary_stream(stream, size, count)
    upload_clk_data_binary(project_id, dp_id, converted_stream, receipt_token, count, size)


@celery.task(base=TracedTask, ignore_result=True, args_as_tags=('project_id', 'dp_id'))
def handle_raw_upload(project_id, dp_id, receipt_token, parent_span=None):
    """
    User has uploaded base64 encodings as JSON, this task needs to copy the data into
    our internal binary format.
    """
    log = logger.bind(pid=project_id, dp_id=dp_id)
    log.info("Handling user provided base64 encodings")
    new_child_span = lambda name: handle_raw_upload.tracer.start_active_span(name, child_of=handle_raw_upload.span)
    with DBConn() as db:
        if not check_project_exists(db, project_id):
            log.info("Project deleted, stopping immediately")
            return
        # Get number of blocks + total number of encodings from database
        expected_count, block_count = get_encoding_metadata(db, dp_id)

    log.info(f"Expecting to handle {expected_count} encodings in {block_count} blocks")
    mc = connect_to_object_store()
    input_filename = Config.RAW_FILENAME_FMT.format(receipt_token)
    raw_data = mc.get_object(Config.MINIO_BUCKET, input_filename)

    with new_child_span('upload-encodings-to-db'):
        # stream encodings with block ids from uploaded file
        # convert each encoding to our internal binary format
        # output into database for each block (temp or direct to minio?)
        encoding_size, pipeline = convert_encodings_from_base64_to_binary(stream_json_clksnblocks(raw_data))
        log.info(f"Starting pipeline to store {encoding_size}B sized encodings in database")
        with DBConn() as db:
            store_encodings_in_db(db, dp_id, pipeline, encoding_size)

    log.info(f"Converted uploaded encodings of size {fmt_bytes(encoding_size)} into internal binary format. Number of blocks: {block_count}")

    # As this is the first time we've seen the encoding size actually uploaded from this data provider
    # We check it complies with the project encoding size.
    try:
        check_dataproviders_encoding(project_id, encoding_size)
    except InvalidEncodingError as e:
        log.warning(e.args[0])
        handle_invalid_encoding_data(project_id, dp_id)

    with DBConn() as conn:
        with new_child_span('save-encoding-metadata'):
            # Save the encoding size as metadata for this data provider
            update_encoding_metadata_set_encoding_size(conn, dp_id, encoding_size)
            update_encoding_metadata(conn, None, dp_id, 'ready')

    # Now work out if all parties have added their data
    if clks_uploaded_to_project(project_id, check_data_ready=True):
        log.info("All parties' data present. Scheduling any queued runs")
        check_for_executable_runs.delay(project_id, handle_raw_upload.get_serialized_span())
