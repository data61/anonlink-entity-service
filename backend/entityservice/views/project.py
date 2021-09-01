import os

from io import BytesIO
import json
import tempfile
import statistics

from connexion import ProblemException
from flask import request
from structlog import get_logger
import opentracing

import entityservice.database as db
from entityservice.encoding_storage import hash_block_name, upload_clk_data_binary, include_encoding_id_in_binary_stream
from entityservice.tasks import handle_raw_upload, remove_project, pull_external_data_encodings_only, \
    pull_external_data, check_for_executable_runs
from entityservice.tracing import serialize_span
from entityservice.utils import fmt_bytes, safe_fail_request, get_json, generate_code, object_store_upload_path, \
    clks_uploaded_to_project
from entityservice.database import DBConn, get_project_column
from entityservice.views.auth_checks import abort_if_project_doesnt_exist, abort_if_invalid_dataprovider_token, \
    abort_if_invalid_results_token, get_authorization_token_type_or_abort, abort_if_inconsistent_upload
from entityservice import models
from entityservice.object_store import connect_to_object_store
from entityservice.serialization import binary_format
from entityservice.settings import Config
from entityservice.views.serialization import ProjectListItem, NewProjectResponse, ProjectDescription
from entityservice.views.util import bind_log_and_span, convert_clks_to_clknblocks, \
    convert_encoding_upload_to_clknblock

logger = get_logger()


def projects_get():
    logger.info("Getting list of all projects")
    with DBConn() as conn:
        projects = db.query_db(conn, 'select project_id, time_added from projects')
    return ProjectListItem(many=True).dump(projects)


def projects_post(project):
    """Create a new project

    There are multiple result types, see documentation for how these effect information leakage
    and the resulting data.
    """
    logger.debug("Processing request to add a new project", project=project)
    try:
        project_model = models.Project.from_json(project)
    except models.InvalidProjectParametersException as e:
        logger.info(f"Denied request to add a new project - {e.msg}", project=project)
        safe_fail_request(400, message=e.msg)

    # Persist the new project
    log = logger.bind(pid=project_model.project_id)
    log.info("Adding new project to database")
    try:
        with DBConn() as conn:
            project_model.save(conn)
    except Exception as e:
        log.warn(e)
        safe_fail_request(500, 'Problem creating new project')

    return NewProjectResponse().dump(project_model), 201


def project_delete(project_id):
    log, parent_span = bind_log_and_span(project_id)
    log.info('Request to delete project')
    # Check the resource exists and hasn't already been marked for deletion
    abort_if_project_doesnt_exist(project_id)

    # Check the caller has a valid results token. Yes it should be renamed.
    abort_if_invalid_results_token(project_id, request.headers.get('Authorization'))
    log.info("Marking project for deletion")

    with DBConn() as db_conn:
        db.mark_project_deleted(db_conn, project_id)

    log.info("Queuing authorized request to delete project resources")
    remove_project.delay(project_id, serialize_span(parent_span))

    return '', 204


def project_get(project_id):
    """
    This endpoint describes a Project.
    """
    log = logger.bind(pid=project_id)
    log.info("Getting detail for a project")
    abort_if_project_doesnt_exist(project_id)
    authorise_get_request(project_id)
    with DBConn() as db_conn:
        project_object = db.get_project(db_conn, project_id)
        # Expose the number of data providers who have uploaded clks
        parties_contributed = db.get_number_parties_uploaded(db_conn, project_id)
        num_parties_with_error = db.get_encoding_error_count(db_conn, project_id)
    log.info(f"{parties_contributed} parties have contributed hashes")
    project_object['parties_contributed'] = parties_contributed

    if num_parties_with_error > 0:
        log.warning(f"There are {num_parties_with_error} parties in error state")
    project_object['error'] = num_parties_with_error > 0

    return ProjectDescription().dump(project_object)


def project_binaryclks_post(project_id):
    """
    Update a project to provide encoded PII data.
    """
    log, parent_span = bind_log_and_span(project_id)
    headers = request.headers
    token = precheck_upload_token(project_id, headers, parent_span)

    with DBConn() as conn:
        dp_id = db.get_dataprovider_id(conn, token)
        project_encoding_size = db.get_project_schema_encoding_size(conn, project_id)
        upload_state_updated = db.is_dataprovider_allowed_to_upload_and_lock(conn, dp_id)

    if not upload_state_updated:
        return safe_fail_request(403, "This token has already been used to upload clks.")

    log = log.bind(dp_id=dp_id)
    log.info("Receiving CLK data.")
    receipt_token = generate_code()

    with opentracing.tracer.start_span('upload-clk-data', child_of=parent_span) as span:
        span.set_tag("project_id", project_id)
        try:
            if headers['Content-Type'] == "application/octet-stream":
                span.set_tag("content-type", 'binary')
                log.info("Handling binary CLK upload")
                try:
                    count, size = check_binary_upload_headers(headers)
                    log.info(f"Headers tell us to expect {count} encodings of {size} bytes")
                    span.log_kv({'count': count, 'size': size})
                except Exception:
                    log.warning("Upload failed due to problem with headers in binary upload")
                    raise
                # Check against project level encoding size (if it has been set)
                if project_encoding_size is not None and size != project_encoding_size:
                    # fail fast - we haven't stored the encoded data yet
                    return safe_fail_request(400, "Upload 'Hash-Size' doesn't match project settings")

                # TODO actually stream the upload data straight to Minio. Currently we can't because
                # connexion has already read the data before our handler is called!
                # https://github.com/zalando/connexion/issues/592
                # stream = get_stream()
                stream = BytesIO(request.data)

                converted_stream = include_encoding_id_in_binary_stream(stream, size, count)

                expected_bytes = size * count
                log.debug(f"Stream size is {len(request.data)} B, and we expect {expected_bytes} B")
                if len(request.data) != expected_bytes:
                    safe_fail_request(400,
                                      "Uploaded data did not match the expected size. Check request headers are correct")
                try:
                    upload_clk_data_binary(project_id, dp_id, converted_stream, receipt_token, count, size, parent_span=span)
                except ValueError:
                    safe_fail_request(400,
                                      "Uploaded data did not match the expected size. Check request headers are correct.")
            else:
                safe_fail_request(400, "Content Type not supported")
        except Exception:
            log.warning("The dataprovider was not able to upload their clks,"
                          " re-enable the corresponding upload token to be used.")

            with DBConn() as conn:
                db.set_dataprovider_upload_state(conn, dp_id, state='error')
            raise
    with DBConn() as conn:
        db.set_dataprovider_upload_state(conn, dp_id, state='done')

    # Now work out if all parties have added their data
    if clks_uploaded_to_project(project_id):
        logger.info("All parties data present. Scheduling any queued runs")
        check_for_executable_runs.delay(project_id, serialize_span(parent_span))


    return {'message': 'Updated', 'receipt_token': receipt_token}, 201


def precheck_upload_token(project_id, headers, parent_span):
    """
    Raise a `ProblemException` if the project doesn't exist or the
    authentication token passed in the headers isn't valid.
    """
    with opentracing.tracer.start_span('check-auth', child_of=parent_span) as span:
        abort_if_project_doesnt_exist(project_id)
        if headers is None or 'Authorization' not in headers:
            safe_fail_request(401, message="Authentication token required")

        token = headers['Authorization']

        # Check the caller has valid token -> otherwise 403
        abort_if_invalid_dataprovider_token(token)
    return token


def project_clks_post(project_id):
    """
    Update a project to provide encoded PII data.
    """

    headers = request.headers

    log, parent_span = bind_log_and_span(project_id)
    log.debug("Starting data upload request")
    token = precheck_upload_token(project_id, headers, parent_span)
    receipt_token = generate_code()
    with DBConn() as conn:
        dp_id = db.get_dataprovider_id(conn, token)
        project_encoding_size = db.get_project_schema_encoding_size(conn, project_id)
        upload_state_updated = db.is_dataprovider_allowed_to_upload_and_lock(conn, dp_id)
        # get flag use_blocking from table projects
        uses_blocking = get_project_column(conn, project_id, 'uses_blocking')

    if not upload_state_updated:
        return safe_fail_request(403, "This token has already been used to upload clks.")

    log = log.bind(dp_id=dp_id)
    log.info("Receiving CLK data.")

    with opentracing.tracer.start_span('upload-clk-data', child_of=parent_span) as span:
        span.set_tag("project_id", project_id)
        try:
            if headers['Content-Type'] == "application/json":
                span.set_tag("content-type", 'json')
                # TODO: Previously, we were accessing the CLKs in a streaming fashion to avoid parsing the json in one hit. This
                #       enables running the web frontend with less memory.
                #       However, as connexion is very, very strict about input validation when it comes to json, it will always
                #       consume the stream first to validate it against the spec. Thus the backflip to fully reading the CLks as
                #       json into memory. -> issue #184
                handle_encoding_upload_json(project_id, dp_id, get_json(), receipt_token, uses_blocking, parent_span=span)

                log.info("Job scheduled to handle users upload")
            elif headers['Content-Type'] == "application/octet-stream":
                span.set_tag("content-type", 'binary')
                log.info("Handling binary CLK upload")
                try:
                    count, size = check_binary_upload_headers(headers)
                    log.info(f"Headers tell us to expect {count} encodings of {size} bytes")
                    span.log_kv({'count': count, 'size': size})
                except Exception:
                    log.warning("Upload failed due to problem with headers in binary upload")
                    raise
                # Check against project level encoding size (if it has been set)
                if project_encoding_size is not None and size != project_encoding_size:
                    # fail fast - we haven't stored the encoded data yet
                    return safe_fail_request(400, "Upload 'Hash-Size' doesn't match project settings")

                # TODO actually stream the upload data straight to Minio. Currently we can't because
                # connexion has already read the data before our handler is called!
                # https://github.com/zalando/connexion/issues/592
                # stream = get_stream()
                stream = BytesIO(request.data)
                expected_bytes = binary_format(size).size * count
                log.debug(f"Stream size is {len(request.data)} B, and we expect {expected_bytes} B")
                if len(request.data) != expected_bytes:
                    safe_fail_request(400, "Uploaded data did not match the expected size. Check request headers are correct")
                try:
                    upload_clk_data_binary(project_id, dp_id, stream, receipt_token, count, size, parent_span=span)
                except ValueError:
                    safe_fail_request(400, "Uploaded data did not match the expected size. Check request headers are correct.")
            else:
                safe_fail_request(400, "Content Type not supported")
        except ProblemException as e:
            # Have an exception that is safe for the user. We reset the upload state to
            # allow the user to try upload again.
            log.info(f"Problem occurred, returning status={e.status} - {e.detail}")
            with DBConn() as conn:
                db.set_dataprovider_upload_state(conn, dp_id, state='not_started')
            raise
        except Exception as e:
            log.warning("Unhandled error occurred during data upload")
            log.exception(e)
            with DBConn() as conn:
                db.set_dataprovider_upload_state(conn, dp_id, state='error')
            safe_fail_request(500, "Sorry, the server couldn't handle that request")


    with DBConn() as conn:
        db.set_dataprovider_upload_state(conn, dp_id, state='done')

    # Now work out if all parties have added their data
    if clks_uploaded_to_project(project_id):
        logger.info("All parties data present. Scheduling any queued runs")
        check_for_executable_runs.delay(project_id, serialize_span(parent_span))

    return {'message': 'Updated', 'receipt_token': receipt_token}, 201


def check_binary_upload_headers(headers):
    if not all(extra_header in headers for extra_header in {'Hash-Count', 'Hash-Size'}):
        safe_fail_request(400, "Binary upload requires 'Hash-Count' and 'Hash-Size' headers")

    def get_header_int(header, min=None, max=None):
        INVALID_HEADER_NUMBER = "Invalid value for {} header".format(header)
        try:
            value = int(headers[header])
            if min is not None and value < min:
                safe_fail_request(400, INVALID_HEADER_NUMBER)
            if max is not None and value > max:
                safe_fail_request(400, INVALID_HEADER_NUMBER)
            return value
        except ValueError:
            safe_fail_request(400, INVALID_HEADER_NUMBER)

    size = get_header_int('Hash-Size', min=Config.MIN_ENCODING_SIZE, max=Config.MAX_ENCODING_SIZE)
    count = get_header_int('Hash-Count', min=1)

    return count, size


def authorise_get_request(project_id):
    if request.headers is None or 'Authorization' not in request.headers:
        safe_fail_request(401, message="Authentication token required")
    auth_header = request.headers.get('Authorization')
    dp_id = None
    # Check the resource exists
    abort_if_project_doesnt_exist(project_id)
    with DBConn() as dbinstance:
        project_object = db.get_project(dbinstance, project_id)
    logger.info("Checking credentials")
    result_type = project_object['result_type']
    if result_type in {'groups', 'similarity_scores'}:
        # Check the caller has a valid results token if we are including results
        abort_if_invalid_results_token(project_id, auth_header)
    elif result_type == 'permutations':
        dp_id = get_authorization_token_type_or_abort(project_id, auth_header)
    else:
        safe_fail_request(500, "Unknown error")
    return dp_id, project_object


def handle_encoding_upload_json(project_id, dp_id, clk_json, receipt_token, uses_blocking, parent_span):
    """
    Take user provided upload information - accepting multiple formats - and eventually
    ingest into the database.

    Encodings uploaded directly in the JSON are first quarantined in the object store,
    and a background task deserializes them.

    Encodings that are in an object store are streamed directly into the database by
    a background task.
    """
    log = logger.bind(pid=project_id)
    log.info("Checking json is consistent")
    try:
        abort_if_inconsistent_upload(uses_blocking, clk_json)
    except ValueError as e:
        safe_fail_request(403, e.args[0])

    if "encodings" in clk_json and 'file' in clk_json['encodings']:
        # external encodings
        log.info("Encodings uploaded via the object store")
        encoding_object_info = clk_json['encodings']['file']
        object_name = encoding_object_info['path']
        _check_object_path_allowed(project_id, dp_id, object_name, log)

        encoding_credentials = clk_json['encodings'].get('credentials')
        # Schedule a background task to pull the encodings from the object store
        # This background task updates the database with encoding metadata assuming
        # that there are no blocks.
        if 'blocks' not in clk_json:
            log.info("scheduling task to pull encodings from object store")
            pull_external_data_encodings_only.delay(
                project_id,
                dp_id,
                encoding_object_info,
                encoding_credentials,
                receipt_token,
                parent_span=serialize_span(parent_span))
        else:
            # Need to deal with both encodings and blocks
            if 'file' in clk_json['blocks']:
                object_name = clk_json['blocks']['file']['path']
                _check_object_path_allowed(project_id, dp_id, object_name, log)
                # Blocks are in an external file
                blocks_object_info = clk_json['blocks']['file']
                blocks_credentials = clk_json['blocks'].get('credentials')
                log.info("scheduling task to pull both encodings and blocking data from object store")
                pull_external_data.delay(
                    project_id,
                    dp_id,
                    encoding_object_info,
                    blocks_object_info,
                    receipt_token,
                    parent_span=serialize_span(parent_span))
            else:
                raise NotImplementedError("Don't currently handle combination of external encodings and blocks")

        return

    # Convert uploaded JSON to common schema.
    #
    # The original JSON API simply accepted "clks", then came a combined encoding and
    # blocking API expecting the top level element "clknblocks". Finally an API that
    # specifies both "encodings" and "blocks" independently at the top level.
    #
    # We rewrite all into the "clknblocks" format.
    if "encodings" in clk_json:
        log.debug("converting from 'encodings' & 'blocks' format to 'clknblocks'")
        clk_json = convert_encoding_upload_to_clknblock(clk_json)

    is_valid_clks = not uses_blocking and 'clks' in clk_json
    element = 'clks' if is_valid_clks else 'clknblocks'

    if len(clk_json[element]) < 1:
        safe_fail_request(400, message="Missing CLKs information")

    filename = Config.RAW_FILENAME_FMT.format(receipt_token)
    log.info("Storing user {} supplied {} from json".format(dp_id, element))

    with opentracing.tracer.start_span('splitting-json-clks', child_of=parent_span) as span:
        encoding_count = len(clk_json[element])
        span.set_tag(element, encoding_count)
        log.debug(f"Received {encoding_count} {element}")

    if element == 'clks':
        log.info("Rewriting provided json into clknsblocks format")
        clk_json = convert_clks_to_clknblocks(clk_json)
        element = 'clknblocks'

    with opentracing.tracer.start_span('Counting block sizes and hashing provided block names', child_of=parent_span) as span:
        log.info("Counting block sizes and hashing provided block names")
        # {'clknblocks': [['UG9vcA==', '001', '211'], [...]]}
        block_sizes = {}
        for _, *elements_blocks in clk_json[element]:
            for el_block in elements_blocks:
                block_id_hash = hash_block_name(el_block)
                block_sizes[block_id_hash] = block_sizes.setdefault(block_id_hash, 0) + 1
        block_count = len(block_sizes)
        span.set_tag('block-count', block_count)

    log.info(f"Received {encoding_count} encodings in {block_count} blocks")
    if block_count > 20:
        #only log summary of block sizes
        log.info(f'info on block sizes. min: {min(block_sizes.values())}, max: {max(block_sizes.values())} mean: {statistics.mean(block_sizes.values())}, median: {statistics.median(block_sizes.values())}')
    else:
        for block in block_sizes:
            logger.info(f"Block {block} has {block_sizes[block]} elements")

    # write clk_json into a temp file
    tmp = tempfile.NamedTemporaryFile(mode='w')
    json.dump(clk_json, tmp)
    tmp.flush()
    clk_filesize = os.stat(tmp.name).st_size
    with opentracing.tracer.start_span('save-clk-file-to-quarantine', child_of=parent_span) as span:
        span.set_tag('filename', filename)
        span.set_tag('filesize', fmt_bytes(clk_filesize))
        mc = connect_to_object_store()
        mc.fput_object(
            Config.MINIO_BUCKET,
            filename,
            tmp.name,
            content_type='application/json'
        )

    log.info('Saved uploaded {} JSON of {} to file {} in object store.'.format(element.upper(), fmt_bytes(clk_filesize), filename))

    with opentracing.tracer.start_span('update-encoding-metadata', child_of=parent_span):
        with DBConn() as conn:
            db.insert_encoding_metadata(conn, filename, dp_id, receipt_token, encoding_count, block_count)
            db.insert_blocking_metadata(conn, dp_id, block_sizes)

    # Schedule a task to deserialize the encodings
    handle_raw_upload.delay(project_id, dp_id, receipt_token, parent_span=serialize_span(parent_span))


def _check_object_path_allowed(project_id, dp_id, object_name, log):
    if not object_name.startswith(object_store_upload_path(project_id, dp_id)):
        log.warning(f"Attempt to upload to illegal path: {object_name}")
        safe_fail_request(403, "Provided object store path is not allowed")
