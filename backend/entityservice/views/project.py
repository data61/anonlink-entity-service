from io import BytesIO
import json
import tempfile

from flask import request
from flask import g
from structlog import get_logger
import opentracing

import entityservice.database as db
from entityservice.encoding_storage import store_encodings_in_db
from entityservice.tasks import handle_raw_upload, check_for_executable_runs, remove_project
from entityservice.tracing import serialize_span
from entityservice.utils import safe_fail_request, get_json, generate_code, clks_uploaded_to_project, fmt_bytes
from entityservice.database import DBConn, get_project_column
from entityservice.views.auth_checks import abort_if_project_doesnt_exist, abort_if_invalid_dataprovider_token, \
    abort_if_invalid_results_token, get_authorization_token_type_or_abort, abort_if_inconsistent_upload
from entityservice import models
from entityservice.object_store import connect_to_object_store
from entityservice.serialization import binary_format
from entityservice.settings import Config
from entityservice.views.serialization import ProjectList, NewProjectResponse, ProjectDescription
from entityservice.views.util import bind_log_and_span

logger = get_logger()

DEFAULT_BLOCK_ID = '1'


def projects_get():
    logger.info("Getting list of all projects")
    with DBConn() as conn:
        projects = db.query_db(conn, 'select project_id, time_added from projects')
    return ProjectList().dump(projects)


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
    log = logger.bind(pid=project_id)
    log.info('Request to delete project')
    # Check the resource exists and hasn't already been marked for deletion
    abort_if_project_doesnt_exist(project_id)

    # Check the caller has a valid results token. Yes it should be renamed.
    abort_if_invalid_results_token(project_id, request.headers.get('Authorization'))
    log.info("Marking project for deletion")

    with DBConn() as db_conn:
        db.mark_project_deleted(db_conn, project_id)

    log.info("Queuing authorized request to delete project resources")
    remove_project.delay(project_id)

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
    receipt_token = None

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
                binary_formatter = binary_format(size)

                def encoding_iterator(filter_stream):
                    # Assumes encoding id and block info not provided (yet)
                    for entity_id in range(count):
                        yield str(entity_id), binary_formatter.pack(entity_id, filter_stream.read(size)), [DEFAULT_BLOCK_ID]

                expected_bytes = size * count
                log.debug(f"Stream size is {len(request.data)} B, and we expect {expected_bytes} B")
                if len(request.data) != expected_bytes:
                    safe_fail_request(400,
                                      "Uploaded data did not match the expected size. Check request headers are correct")
                try:
                    receipt_token = upload_clk_data_binary(project_id, dp_id, encoding_iterator(stream), count, size)
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

    token = precheck_upload_token(project_id, headers, parent_span)

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
    receipt_token = None

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
                receipt_token, raw_file = upload_json_clk_data(dp_id, get_json(), uses_blocking, parent_span=span)
                # Schedule a task to deserialize the hashes, and carry
                # out a pop count.
                handle_raw_upload.delay(project_id, dp_id, receipt_token, parent_span=serialize_span(span))
                log.info("Job scheduled to handle user uploaded hashes")
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
                    receipt_token = upload_clk_data_binary(project_id, dp_id, stream, count, size)
                except ValueError:
                    safe_fail_request(400, "Uploaded data did not match the expected size. Check request headers are correct.")
            else:
                safe_fail_request(400, "Content Type not supported")
        except Exception:
            log.info("The dataprovider was not able to upload her clks,"
                     " re-enable the corresponding upload token to be used.")
            with DBConn() as conn:
                db.set_dataprovider_upload_state(conn, dp_id, state='error')
            raise
    with DBConn() as conn:
        db.set_dataprovider_upload_state(conn, dp_id, state='done')
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


def upload_clk_data_binary(project_id, dp_id, encoding_iter, count, size=128):
    """
    Save the user provided binary-packed CLK data.

    """
    receipt_token = generate_code()
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

    # Now work out if all parties have added their data
    if clks_uploaded_to_project(project_id):
        logger.info("All parties data present. Scheduling any queued runs")
        check_for_executable_runs.delay(project_id, serialize_span(parent_span))

    return receipt_token


def upload_json_clk_data(dp_id, clk_json, uses_blocking, parent_span):
    """
    Take user provided encodings as json dict and save them, as-is, to the object store.

    Note this implementation is non-streaming.
    """
    try:
        abort_if_inconsistent_upload(uses_blocking, clk_json)
    except ValueError as e:
        safe_fail_request(403, e)

    # now we need to know element name - clks or clknblocks
    is_valid_clks = not uses_blocking and 'clks' in clk_json
    element = 'clks' if is_valid_clks else 'clknblocks'

    if len(clk_json[element]) < 1:
        safe_fail_request(400, message="Missing CLKs information")

    receipt_token = generate_code()

    filename = Config.RAW_FILENAME_FMT.format(receipt_token)
    logger.info("Storing user {} supplied {} from json".format(dp_id, element))

    with opentracing.tracer.start_span('splitting-json-clks', child_of=parent_span) as span:
        encoding_count = len(clk_json[element])
        span.set_tag(element, encoding_count)
        logger.debug(f"Received {encoding_count} {element}")

    if element == 'clks':
        logger.info("Rewriting provided json into clknsblocks format")
        clk_json = {'clknblocks': [[encoding, '1'] for encoding in clk_json['clks']]}
        element = 'clknblocks'

    logger.info("Counting block sizes and number of blocks")
    # {'clknblocks': [['UG9vcA==', '001', '211'], [...]]}
    block_sizes = {}
    for _, *elements_blocks in clk_json[element]:
        for el_block in elements_blocks:
            block_sizes[el_block] = block_sizes.setdefault(el_block, 0) + 1
    block_count = len(block_sizes)

    logger.info(f"Received {encoding_count} encodings in {block_count} blocks")
    for block in block_sizes:
        logger.info(f"Block {block} has {block_sizes[block]} elements")

    # write clk_json into a temp file
    tmp = tempfile.NamedTemporaryFile(mode='w')
    json.dump(clk_json, tmp)
    tmp.flush()
    with opentracing.tracer.start_span('save-clk-file-to-quarantine', child_of=parent_span) as span:
        span.set_tag('filename', filename)
        mc = connect_to_object_store()
        mc.fput_object(
            Config.MINIO_BUCKET,
            filename,
            tmp.name,
            content_type='application/json'
        )
    logger.info('Saved uploaded {} JSON to file {} in object store.'.format(element.upper(), filename))

    with opentracing.tracer.start_span('update-encoding-metadata', child_of=parent_span):
        with DBConn() as conn:
            db.insert_encoding_metadata(conn, filename, dp_id, receipt_token, encoding_count, block_count)
            db.insert_blocking_metadata(conn, dp_id, block_sizes)

    return receipt_token, filename
