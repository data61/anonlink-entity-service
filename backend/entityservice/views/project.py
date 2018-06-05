import io
from io import BytesIO

import minio
from flask import request
import entityservice.database as db

from entityservice.async_worker import handle_raw_upload, check_for_executable_runs
from entityservice import app, fmt_bytes
from entityservice.utils import safe_fail_request, get_json, generate_code, get_stream, clks_uploaded_to_project

from entityservice.database import get_db
from entityservice.views.auth_checks import abort_if_project_doesnt_exist, abort_if_invalid_dataprovider_token, \
    abort_if_invalid_results_token, dataprovider_id_if_authorize, get_authorization_token_type_or_abort
from entityservice import models
from entityservice.object_store import connect_to_object_store
from entityservice.settings import Config as config
from entityservice.views.serialization import ProjectList, NewProjectResponse, ProjectDescription


def projects_get():

    app.logger.info("Getting list of all projects")
    projects = db.query_db(get_db(), 'select project_id, time_added from projects')
    return ProjectList().dump(projects)


def projects_post(project):
    """Create a new project

    There are multiple result types, see documentation for how these effect information leakage
    and the resulting data.
    """
    try:
        project_model = models.Project.from_json(project)
    except models.InvalidProjectParametersException as e:
        safe_fail_request(400, message=e.msg)

    # Persist the new project
    app.logger.info("Adding new project to database")

    try:
        project_model.save(get_db())
    except Exception as e:
        app.logger.warn(e)
        safe_fail_request(500, 'Problem creating new project')

    return NewProjectResponse().dump(project_model), 201


def project_delete(project_id):
    app.logger.debug("Request to delete project with id {}".format(project_id))
    # Check the resource exists
    abort_if_project_doesnt_exist(project_id)

    # Check the caller has a valid results token. Yes it should be renamed.
    abort_if_invalid_results_token(project_id, request.headers.get('Authorization'))

    dbinstance = get_db()
    mc = connect_to_object_store()
    project_from_db = db.get_project(dbinstance, project_id)

    app.logger.info("Authorized request to delete a project resource and all data")

    # If result_type is similarity_scores, delete the corresponding similarity_scores file
    if project_from_db['result_type'] == 'similarity_scores':
        app.logger.info("Deleting the similarity scores file from object store")
        filename = db.get_similarity_scores_filename(dbinstance, project_id)
        mc.remove_object(config.MINIO_BUCKET, filename)

    app.logger.info("Deleting project resourced from database")
    object_store_files = db.delete_project(get_db(), project_id)
    app.logger.info("Object store files associated with project:")

    for filename in object_store_files:
        app.logger.info("Deleting {}".format(filename))
        mc.remove_object(config.MINIO_BUCKET, filename)

    return '', 204


def project_get(project_id):
    """
    This endpoint describes a Project.
    """
    app.logger.info("Getting detail for a project")
    abort_if_project_doesnt_exist(project_id)
    authorise_get_request(project_id)
    db_conn = db.get_db()
    project_object = db.get_project(db_conn, project_id)

    # Expose the number of data providers who have uploaded clks
    parties_contributed = db.get_number_parties_uploaded(db_conn, project_id)
    app.logger.info("{} parties have contributed hashes".format(parties_contributed))
    project_object['parties_contributed'] = parties_contributed

    return ProjectDescription().dump(project_object)


def project_clks_post(project_id):
    """
    Update a project to provide data.
    """

    headers = request.headers

    abort_if_project_doesnt_exist(project_id)
    if headers is None or 'Authorization' not in headers:
        safe_fail_request(401, message="Authentication token required")

    token = headers['Authorization']

    # Check the caller has valid token -> otherwise 403
    abort_if_invalid_dataprovider_token(token)

    dp_id = db.get_dataprovider_id(get_db(), token)

    app.logger.info("Receiving data for: dpid: {}".format(dp_id))

    if headers['Content-Type'] == "application/json":
        # TODO: Previously, we were accessing the CLKs in a streaming fashion to avoid parsing the json in one hit. This
        #       enables running the web frontend with less memory.
        #       However, as connexion is very, very strict about input validation when it comes to json, it will always
        #       consume the stream first to validate it against the spec. Thus the backflip to fully reading the CLks as
        #       json into memory. -> issue #184
        receipt_token, raw_file = upload_json_clk_data(dp_id, get_json())
        # Schedule a task to deserialize the hashes, and carry
        # out a pop count.
        handle_raw_upload.delay(project_id, dp_id, receipt_token)
        app.logger.info("Job scheduled to handle user uploaded hashes")
    elif headers['Content-Type'] == "application/octet-stream":
        app.logger.info("Handling binary CLK upload")
        try:
            count, size = check_binary_upload_headers(headers)
        except:
            app.logger.info("Upload failed due to problem with headers in binary upload")
            raise

        # TODO actually stream the upload data straight to Minio. Currently we can't because
        # connexion has already read the data before our handler is called!
        # https://github.com/zalando/connexion/issues/592
        #stream = get_stream()
        stream = BytesIO(request.data)
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

    size = get_header_int('Hash-Size', min=1)
    count = get_header_int('Hash-Count', min=1)
    if size != 128:
        safe_fail_request(400, "We don't currently support a CLK size other than 128 bytes")
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
    app.logger.info("Checking credentials")
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
    filename = config.RAW_FILENAME_FMT.format(receipt_token)
    # Set the state to 'pending' in the bloomingdata table
    db.insert_filter_data(get_db(), filename, dp_id, receipt_token, count)
    app.logger.info("dp_id={} Storing supplied binary clks".format(dp_id))

    num_bytes = count * (size + 6)

    app.logger.debug("Directly storing binary file with index, base64 encoded CLK, popcount")

    # Upload to object store
    app.logger.info("Uploading binary packed clks to object store. Size: {}".format(fmt_bytes(num_bytes)))
    mc = connect_to_object_store()
    try:
        mc.put_object(config.MINIO_BUCKET, filename, data=raw_stream, length=num_bytes)
    except (minio.error.InvalidSizeError, minio.error.InvalidArgumentError):
        app.logger.info("Mismatch between expected stream length and header info")
        raise ValueError("Mismatch between expected stream length and header info")

    db.update_filter_data(get_db(), filename, dp_id, 'ready')
    db.set_dataprovider_upload_state(get_db(), dp_id, True)

    # Now work out if all parties have added their data
    if clks_uploaded_to_project(project_id):
        app.logger.info("Project {} - All parties data present. Scheduling any queued runs".format(project_id))
        check_for_executable_runs.delay(project_id)

    return receipt_token


def upload_json_clk_data(dp_id, clk_json):
    """
    non-streaming version of the upload_clk_data from above.
    """
    if 'clks' not in clk_json or len(clk_json['clks']) < 1:
        safe_fail_request(400, message="Missing CLKs information")

    receipt_token = generate_code()

    filename = config.RAW_FILENAME_FMT.format(receipt_token)
    app.logger.info("Storing user {} supplied clks from json".format(dp_id))

    count = len(clk_json['clks'])
    data = b''.join(''.join(clk.split('\n')).encode() + b'\n' for clk in clk_json['clks'])

    num_bytes = len(data)
    buffer = io.BytesIO(data)

    app.logger.info("Processed {} CLKS".format(count))
    app.logger.info("Uploading {} to object store".format(fmt_bytes(num_bytes)))
    mc = connect_to_object_store()
    mc.put_object(
        config.MINIO_BUCKET,
        filename,
        data=buffer,
        length=len(data)
    )

    db.insert_filter_data(get_db(), filename, dp_id, receipt_token, count)

    return receipt_token, filename
