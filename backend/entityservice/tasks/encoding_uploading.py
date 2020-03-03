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

    log.info(f"Converted uploaded encodings of size {encoding_size} bytes into internal binary format. Number of blocks: {block_count}")

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
