import io

import opentracing

from entityservice.database import *
from entityservice.encoding_storage import stream_json_clksnblocks, convert_encodings_from_base64_to_binary, \
    convert_encodings_from_json_to_binary, store_encodings_in_db
from entityservice.error_checking import check_dataproviders_encoding, handle_invalid_encoding_data, \
    InvalidEncodingError
from entityservice.object_store import connect_to_object_store
from entityservice.serialization import binary_format
from entityservice.settings import Config
from entityservice.async_worker import celery, logger
from entityservice.tasks.base_task import TracedTask
from entityservice.tasks.pre_run_check import check_for_executable_runs
from entityservice.utils import fmt_bytes, clks_uploaded_to_project


@celery.task(base=TracedTask, ignore_result=True, args_as_tags=('project_id', 'dp_id'))
def handle_raw_upload(project_id, dp_id, receipt_token, parent_span=None):
    """
    User has uploaded base64 encodings as JSON, this task needs to copy the data into
    our internal binary format.
    """
    log = logger.bind(pid=project_id, dp_id=dp_id)
    log.info("Handling user provided base64 encodings")

    with DBConn() as db:
        if not check_project_exists(db, project_id):
            log.info("Project deleted, stopping immediately")
            return
        # Get number of blocks + total number of encodings from database
        expected_count, block_count = get_encoding_metadata(db, dp_id)

    log.info(f"Expecting to handle {expected_count} encodings in {block_count} blocks")
    mc = connect_to_object_store()
    raw_file = Config.RAW_FILENAME_FMT.format(receipt_token)
    raw_data = mc.get_object(Config.MINIO_BUCKET, raw_file)

    with opentracing.tracer.start_span('upload-encodings-to-db', child_of=parent_span):
        # stream encodings with block ids from uploaded file
        # convert each encoding to our internal binary format
        # output into database for each block (temp or direct to minio?)
        encoding_size, pipeline = convert_encodings_from_base64_to_binary(stream_json_clksnblocks(raw_data))
        log.info(f"Starting pipeline to store {encoding_size}B sized encodings in database")
        with DBConn() as db:
            store_encodings_in_db(db, dp_id, pipeline, encoding_size)

    #### GLUE CODE - TODO remove me once moved away from storing encodings in files
    # Note we open the stream a second time
    raw_data = mc.get_object(Config.MINIO_BUCKET, raw_file)
    blocked_binary_data, encoding_size = convert_encodings_from_json_to_binary(raw_data)
    assert block_count == len(blocked_binary_data)
    log.info(f"Converted uploaded encodings of size {encoding_size} bytes into internal binary format. Number of blocks: {block_count}")

    if block_count == 0:
        log.warning("No uploaded encoding blocks, stopping processing.")
        # TODO mark run as failure?
        return
    elif block_count > 1:
        raise NotImplementedError('Currently handle single block encodings - check back soon')

    #for block_id in blocked_binary_data:
    block_id = list(blocked_binary_data.keys())[0]
    actual_count = len(blocked_binary_data[block_id])
    log.info(f"{block_id=}, number of encodings: {actual_count}")

    # We peek at the first element as we need the encoding size
    # for the rest of our processing pipeline. Note we now add 4 bytes to the encoding
    # for the entity's identifier.
    uploaded_encoding_size = len(blocked_binary_data[block_id][0]) - 4

    # This is the first time we've seen the encoding size from this data provider
    try:
        check_dataproviders_encoding(project_id, uploaded_encoding_size)
    except InvalidEncodingError as e:
        log.warning(e.args[0])
        handle_invalid_encoding_data(project_id, dp_id)

    with DBConn() as db:
        # Save the encoding size as metadata
        update_encoding_metadata_set_encoding_size(db, dp_id, uploaded_encoding_size)

    # Output file is our custom binary packed file
    filename = Config.BIN_FILENAME_FMT.format(receipt_token)
    bit_packed_element_size = binary_format(uploaded_encoding_size).size
    num_bytes = actual_count * bit_packed_element_size

    with opentracing.tracer.start_span('process-encodings-in-quarantine', child_of=parent_span) as span:
        packed_filter_stream = io.BytesIO(b''.join(blocked_binary_data[block_id]))
        # Upload to object store
        log.info(f"Uploading {expected_count} encodings of size {uploaded_encoding_size} " +
                 f"to object store. Total Size: {fmt_bytes(num_bytes)}")
        mc.put_object(Config.MINIO_BUCKET, filename, data=packed_filter_stream, length=num_bytes)

    with DBConn() as conn:
        update_encoding_metadata(conn, filename, dp_id, 'ready')

    # Now work out if all parties have added their data
    if clks_uploaded_to_project(project_id, check_data_ready=True):
        log.info("All parties' data present. Scheduling any queued runs")
        check_for_executable_runs.delay(project_id, handle_raw_upload.get_serialized_span())
