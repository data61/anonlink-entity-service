import json
import ijson
from requests.structures import CaseInsensitiveDict

from entityservice.database import *
from entityservice.encoding_storage import hash_block_name, stream_json_clksnblocks, \
    convert_encodings_from_base64_to_binary, \
    store_encodings_in_db, upload_clk_data_binary, include_encoding_id_in_binary_stream, \
    include_encoding_id_in_json_stream
from entityservice.error_checking import check_dataproviders_encoding, handle_invalid_encoding_data, \
    InvalidEncodingError
from entityservice.object_store import connect_to_object_store, stat_and_stream_object, delete_object_store_files
from entityservice.serialization import binary_format, deserialize_bytes
from entityservice.settings import Config
from entityservice.async_worker import celery
from entityservice.tasks.base_task import TracedTask
from entityservice.tasks.pre_run_check import check_for_executable_runs
from entityservice.tracing import serialize_span
from entityservice.utils import fmt_bytes, clks_uploaded_to_project

logger = get_logger()


@celery.task(base=TracedTask, ignore_result=True, args_as_tags=('project_id', 'dp_id'))
def pull_external_data(project_id, dp_id,
                       encoding_object_info,
                       blocks_object_info,
                       receipt_token, parent_span=None):
    """
    Load encoding and blocking data from object store.

    - pull blocking map into memory, create blocks in db
    - stream encodings into DB and add encoding + blocks from in memory dict.
    - delete files on object store

    :param project_id: identifier for the project
    :param dp_id:
    :param encoding_object_info: a dictionary contains bucket and path of uploaded encoding
    :param blocks_object_info: a dictionary contains bucket and path of uploaded blocks
    :param receipt_token: token used to insert into database

    """
    log = logger.bind(pid=project_id, dp_id=dp_id)
    mc = connect_to_object_store()

    with DBConn() as conn:
        if not check_project_exists(conn, project_id):
            log.info("Project deleted, stopping immediately")
            delete_object_store_files(mc, [encoding_object_info, blocks_object_info])
            return

    log.debug("Pulling blocking information from object store")

    response = mc.get_object(bucket_name=blocks_object_info['bucket'], object_name=blocks_object_info['path'])
    log.debug("Counting the blocks and hashing block names")
    block_sizes = {}
    encoding_to_block_map = {}
    for k, v in ijson.kvitems(response.data, 'blocks'):
        # k is 0, v is ['3', '0']
        _blocks = list(map(hash_block_name, v))
        encoding_to_block_map[str(k)] = _blocks
        for block_hash in _blocks:
            block_sizes[block_hash] = block_sizes.setdefault(block_hash, 0) + 1

    block_count = len(block_sizes)
    log.debug(f"Processing {block_count} blocks")

    # stream the encodings
    bucket_name = encoding_object_info['bucket']
    object_name = encoding_object_info['path']

    stat, encodings_stream = stat_and_stream_object(bucket_name, object_name)
    stat_metadata = CaseInsensitiveDict(stat.metadata)
    count = int(stat_metadata['X-Amz-Meta-Hash-Count'])
    size = int(stat_metadata['X-Amz-Meta-Hash-Size'])
    log.debug(f"Processing {count} encodings of size {size}")
    assert count == len(encoding_to_block_map), f"Expected {count} encodings in blocks got {len(encoding_to_block_map)}"

    with DBConn() as conn:
        with opentracing.tracer.start_span('update-metadata-db', child_of=parent_span):
            insert_encoding_metadata(conn, None, dp_id, receipt_token, encoding_count=count, block_count=block_count)
            update_encoding_metadata_set_encoding_size(conn, dp_id, size)
        with opentracing.tracer.start_span('create-block-entries-in-db', child_of=parent_span):
            log.debug("Adding blocks to db")
            insert_blocking_metadata(conn, dp_id, block_sizes)

        def ijson_encoding_iterator(encoding_stream):
            binary_formatter = binary_format(size)
            for encoding_id, encoding in zip(range(count), encoding_stream):
                yield (
                    str(encoding_id),
                    binary_formatter.pack(encoding_id, deserialize_bytes(encoding)),
                    encoding_to_block_map[str(encoding_id)]
                    )

        def encoding_iterator(encoding_stream):
            binary_formatter = binary_format(size)
            for encoding_id in range(count):
                yield (
                    str(encoding_id),
                    binary_formatter.pack(encoding_id, encoding_stream.read(size)),
                    encoding_to_block_map[str(encoding_id)]
                    )

        if object_name.endswith('.json'):
            log.info("Have json file of encodings")
            encodings_stream = ijson.items(io.BytesIO(encodings_stream.data), 'clks.item')
            encoding_generator = ijson_encoding_iterator(encodings_stream)
        else:
            log.info("Have binary file of encodings")
            encoding_generator = encoding_iterator(encodings_stream)

        with opentracing.tracer.start_span('upload-encodings-to-db', child_of=parent_span):
            log.debug("Adding encodings and associated blocks to db")
            try:
                store_encodings_in_db(conn, dp_id, encoding_generator, size)
            except Exception as e:
                log.warning("Failed while adding encodings and associated blocks to db", exc_info=e)

                update_dataprovider_uploaded_state(conn, project_id, dp_id, 'error')
                raise e

        with opentracing.tracer.start_span('update-encoding-metadata', child_of=parent_span):
            update_encoding_metadata(conn, None, dp_id, 'ready')
            update_blocks_state(conn, dp_id, block_sizes.keys(), 'ready')

    delete_object_store_files(mc, [encoding_object_info, blocks_object_info])
    # # Now work out if all parties have added their data
    if clks_uploaded_to_project(project_id):
        logger.info("All parties data present. Scheduling any queued runs")
        check_for_executable_runs.delay(project_id, serialize_span(parent_span))


@celery.task(base=TracedTask, ignore_result=True, args_as_tags=('project_id', 'dp_id'))
def pull_external_data_encodings_only(project_id, dp_id, object_info, credentials, receipt_token, parent_span=None):
    """
    for now, we only pull from the entity service's object store.
    """
    log = logger.bind(pid=project_id, dp_id=dp_id)

    with DBConn() as conn:
        if not check_project_exists(conn, project_id):
            log.info("Project deleted, stopping immediately")
            delete_object_store_files(connect_to_object_store(), [object_info])
            return

    bucket_name = object_info['bucket']
    object_name = object_info['path']

    stat, stream = stat_and_stream_object(bucket_name, object_name)
    stat_metadata = CaseInsensitiveDict(stat.metadata)

    count = int(stat_metadata['X-Amz-Meta-Hash-Count'])
    size = int(stat_metadata['X-Amz-Meta-Hash-Size'])

    if object_name.endswith('.json'):
        log.info("treating file as json")
        encodings_stream = ijson.items(io.BytesIO(stream.data), 'clks.item')
        converted_stream = include_encoding_id_in_json_stream(encodings_stream, size, count)
    else:
        log.info("treating file as binary")
        converted_stream = include_encoding_id_in_binary_stream(stream, size, count)
    upload_clk_data_binary(project_id, dp_id, converted_stream, receipt_token, count, size, parent_span=parent_span)

    delete_object_store_files(connect_to_object_store(), [object_info])
    # # Now work out if all parties have added their data
    if clks_uploaded_to_project(project_id):
        log.info("All parties data present. Scheduling any queued runs")
        check_for_executable_runs.delay(project_id, serialize_span(parent_span))


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
        log.info(f"checking that {encoding_size} is okay for this project")
        check_dataproviders_encoding(project_id, encoding_size)
    except InvalidEncodingError as e:
        log.warning("Encoding size doesn't seem right")
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


@celery.task(base=TracedTask, ignore_result=True, args_as_tags=('project_id', 'dp_id'))
def handle_upload_error(*args, project_id, dp_id, receipt_token, parent_span=None):
    log = logger.bind(pid=project_id, dp_id=dp_id)
    if len(args) == 3:
        request, exc, traceback = args
        log.warning(f"Upload failed with: {exc}")
    with DBConn() as conn:
        update_upload_state(conn, dp_id, receipt_token, 'error')
        log.warning("set upload state to 'error'")
