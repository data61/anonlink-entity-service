import io
from io import BytesIO

import minio
from flask import request
from flask import g
from structlog import get_logger
import opentracing

import entityservice.database as db
from entityservice.async_worker import handle_raw_upload, check_for_executable_runs
from entityservice import app, fmt_bytes
from entityservice.tasks.project_cleanup import delete_project
from entityservice.tracing import serialize_span
from entityservice.utils import safe_fail_request, get_json, generate_code, get_stream, clks_uploaded_to_project

from entityservice.database import get_db
from entityservice.views.auth_checks import abort_if_project_doesnt_exist, abort_if_invalid_dataprovider_token, \
    abort_if_invalid_results_token, get_authorization_token_type_or_abort
from entityservice import models
from entityservice.object_store import connect_to_object_store
from entityservice.settings import Config as config
from entityservice.views.serialization import ProjectList, NewProjectResponse, ProjectDescription

logger = get_logger()


def projects_get():
    logger.info("Getting list of all projects")
    projects = db.query_db(get_db(), 'select project_id, time_added from projects')
    return ProjectList().dump(projects)


def projects_post(project):
    """Create a new project

    There are multiple result types, see documentation for how these effect information leakage
    and the resulting data.
    """
    logger = get_logger()
    logger.debug("Processing request to add a new project", project=project)
    try:
        project_model = models.Project.from_json(project)
        logger = logger.bind(pid=project_model.project_id)
    except models.InvalidProjectParametersException as e:
        safe_fail_request(400, message=e.msg)

    # Persist the new project
    logger.info("Adding new project to database")

    try:
        project_model.save(get_db())
    except Exception as e:
        logger.warn(e)
        safe_fail_request(500, 'Problem creating new project')

    return NewProjectResponse().dump(project_model), 201


def project_delete(project_id):
    log = logger.bind(pid=project_id)
    log.info('Request to delete project')
    # Check the resource exists and hasn't already been marked for deletion
    abort_if_project_doesnt_exist(project_id)

    # Check the caller has a valid results token. Yes it should be renamed.
    abort_if_invalid_results_token(project_id, request.headers.get('Authorization'))
    log.info("Queuing authorized request to delete project resources")

    dbinstance = get_db()
    db.mark_project_deleted(dbinstance, project_id)

    delete_project.delay(project_id)

    return '', 204


def project_get(project_id):
    """
    This endpoint describes a Project.
    """
    log = logger.bind(pid=project_id)
    log.info("Getting detail for a project")
    abort_if_project_doesnt_exist(project_id)
    authorise_get_request(project_id)
    db_conn = db.get_db()
    project_object = db.get_project(db_conn, project_id)

    # Expose the number of data providers who have uploaded clks
    parties_contributed = db.get_number_parties_uploaded(db_conn, project_id)
    log.info(f"{parties_contributed} parties have contributed hashes")
    project_object['parties_contributed'] = parties_contributed

    num_parties_with_error = db.get_encoding_error_count(db_conn, project_id)
    if num_parties_with_error > 0:
        log.warning(f"There are {num_parties_with_error} parties in error state")
    project_object['error'] = num_parties_with_error > 0

    return ProjectDescription().dump(project_object)


def project_clks_post(project_id):
    """
    Update a project to provide encoded PII data.
    """
    log = logger.bind(pid=project_id)
    headers = request.headers

    parent_span = g.flask_tracer.get_span()

    with opentracing.tracer.start_span('check-auth', child_of=parent_span) as span:
        abort_if_project_doesnt_exist(project_id)
        if headers is None or 'Authorization' not in headers:
            safe_fail_request(401, message="Authentication token required")

        token = headers['Authorization']

        # Check the caller has valid token -> otherwise 403
        abort_if_invalid_dataprovider_token(token)

    dp_id = db.get_dataprovider_id(get_db(), token)

    log = log.bind(dp_id=dp_id)
    log.info("Receiving CLK data.")
    with opentracing.tracer.start_span('upload-data', child_of=parent_span) as span:
        span.set_tag("project_id", project_id)
        if headers['Content-Type'] == "application/json":
            span.set_tag("content-type", 'json')
            # TODO: Previously, we were accessing the CLKs in a streaming fashion to avoid parsing the json in one hit. This
            #       enables running the web frontend with less memory.
            #       However, as connexion is very, very strict about input validation when it comes to json, it will always
            #       consume the stream first to validate it against the spec. Thus the backflip to fully reading the CLks as
            #       json into memory. -> issue #184

            receipt_token, raw_file = upload_json_clk_data(dp_id, get_json(), span)
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
            except:
                log.warning("Upload failed due to problem with headers in binary upload")
                raise

            # TODO actually stream the upload data straight to Minio. Currently we can't because
            # connexion has already read the data before our handler is called!
            # https://github.com/zalando/connexion/issues/592
            #stream = get_stream()
            stream = BytesIO(request.data)
            log.debug(f"Stream size is {len(request.data)} B, and we expect {(6 + size)* count} B")
            if len(request.data) != (6 + size) * count:
                safe_fail_request(400, "Uploaded data did not match the expected size. Check request headers are correct")
            try:
                receipt_token = upload_clk_data_binary(project_id, dp_id, stream, count, size)
            except ValueError:
                safe_fail_request(400, "Uploaded data did not match the expected size. Check request headers are correct.")
        else:
            safe_fail_request(400, "Content Type not supported")

    return {'message': 'Updated', 'receipt_token': receipt_token}, 201


def check_binary_upload_headers(headers):
    if not all(extra_header in headers for extra_header in {'Hash-Count', 'Hash-Size'}):
        safe_fail_request(400, "Binary upload requires 'Hash-Count' and 'Hash-Size' headers")

    def get_header_int(header, min=None, max=None):
        INVALID_HEADER_NUMBER = "Invalid value for {} header".format(header)
        try:
            value = int(headers[header])
        except ValueError:
            safe_fail_request(400, INVALID_HEADER_NUMBER)

        if min is not None and value < min:
            safe_fail_request(400, INVALID_HEADER_NUMBER)
        if max is not None and value > max:
            safe_fail_request(400, INVALID_HEADER_NUMBER)
        return value

    size = get_header_int('Hash-Size', min=config.MIN_ENCODING_SIZE, max=config.MAX_ENCODING_SIZE)
    count = get_header_int('Hash-Count', min=1)

    return count, size


def authorise_get_request(project_id):
    if request.headers is None or 'Authorization' not in request.headers:
        safe_fail_request(401, message="Authentication token required")
    auth_header = request.headers.get('Authorization')
    dp_id = None
    # Check the resource exists
    abort_if_project_doesnt_exist(project_id)
    dbinstance = get_db()
    project_object = db.get_project(dbinstance, project_id)
    logger.info("Checking credentials")
    if project_object['result_type'] == 'mapping' or project_object['result_type'] == 'similarity_scores':
        # Check the caller has a valid results token if we are including results
        abort_if_invalid_results_token(project_id, auth_header)
    elif project_object['result_type'] == 'permutations':
        dp_id = get_authorization_token_type_or_abort(project_id, auth_header)
    else:
        safe_fail_request(500, "Unknown error")
    return dp_id, project_object


def upload_clk_data_binary(project_id, dp_id, raw_stream, count, size=128):
    """
    Save the user provided raw CLK data.

    """
    receipt_token = generate_code()
    filename = config.BIN_FILENAME_FMT.format(receipt_token)
    # Set the state to 'pending' in the bloomingdata table
    with db.DBConn() as conn:
        db.insert_filter_data(conn, filename, dp_id, receipt_token, count, size)
    logger.info(f"Storing supplied binary clks of individual size {size} in file: {filename}")

    num_bytes = count * (size + 6)

    logger.debug("Directly storing binary file with index, base64 encoded CLK, popcount")

    # Upload to object store
    logger.info(f"Uploading {count} binary encodings to object store. Total size: {fmt_bytes(num_bytes)}")
    parent_span = g.flask_tracer.get_span()

    with opentracing.tracer.start_span('save-to-minio', child_of=parent_span) as span:
        mc = connect_to_object_store()
        try:
            mc.put_object(config.MINIO_BUCKET, filename, data=raw_stream, length=num_bytes)
        except (minio.error.InvalidSizeError, minio.error.InvalidArgumentError, minio.error.ResponseError):
            logger.info("Mismatch between expected stream length and header info")
            raise ValueError("Mismatch between expected stream length and header info")

    with opentracing.tracer.start_span('update-database', child_of=parent_span) as span:
        with db.DBConn() as conn:
            db.update_filter_data(conn, filename, dp_id, 'ready')
            db.set_dataprovider_upload_state(conn, dp_id, True)

    # Now work out if all parties have added their data
    if clks_uploaded_to_project(project_id):
        logger.info("All parties data present. Scheduling any queued runs")
        check_for_executable_runs.delay(project_id, serialize_span(parent_span))

    return receipt_token


def upload_json_clk_data(dp_id, clk_json, parent_span):
    """
    Convert user provided encodings from json array of base64 data into
    a newline separated file of base64 data.

    Note this implementation is non-streaming.
    """
    if 'clks' not in clk_json or len(clk_json['clks']) < 1:
        safe_fail_request(400, message="Missing CLKs information")

    receipt_token = generate_code()

    filename = config.RAW_FILENAME_FMT.format(receipt_token)
    logger.info("Storing user {} supplied clks from json".format(dp_id))

    with opentracing.tracer.start_span('clk-splitting', child_of=parent_span) as span:
        count = len(clk_json['clks'])
        span.set_tag("clks", count)
        data = b''.join(''.join(clk.split('\n')).encode() + b'\n' for clk in clk_json['clks'])

        num_bytes = len(data)
        span.set_tag("num_bytes", num_bytes)
        buffer = io.BytesIO(data)

    logger.info(f"Received {count} encodings. Uploading {fmt_bytes(num_bytes)} to object store")
    with opentracing.tracer.start_span('save-to-quarantine', child_of=parent_span) as span:
        span.set_tag('filename', filename)
        mc = connect_to_object_store()
        mc.put_object(
            config.MINIO_BUCKET,
            filename,
            data=buffer,
            length=num_bytes
        )

    with opentracing.tracer.start_span('update-db', child_of=parent_span) as span:
        with db.DBConn() as conn:
            db.insert_filter_data(conn, filename, dp_id, receipt_token, count, size=-1)

    return receipt_token, filename
