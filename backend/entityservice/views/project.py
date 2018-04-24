import io

from flask import request
from flask_restful import Resource, abort, fields, marshal, marshal_with
from ijson.backends import yajl2_cffi as ijson

import entityservice.cache as cache
import entityservice.database as db

from entityservice.async_worker import handle_raw_upload
from entityservice import app, fmt_bytes
from entityservice.utils import safe_fail_request, get_stream, get_json, generate_code

from entityservice.database import get_db
from entityservice.views.auth_checks import abort_if_project_doesnt_exist, abort_if_invalid_dataprovider_token, \
    abort_if_invalid_results_token, dataprovider_id_if_authorize, node_id_if_authorize
from entityservice import models
from entityservice.object_store import connect_to_object_store
from entityservice.settings import Config as config


new_project_response_fields = {
    'project_id': fields.String,
    'result_token': fields.String,
    'update_tokens': fields.List(fields.String)
}


class ProjectList(Resource):
    """
    Top level project endpoint.

    GET /projects       A list of all projects.
    POST /projects      Create a new project

    """

    def get(self):
        project_resource_fields = {
            'project_id': fields.String,
            'time_added': fields.DateTime(dt_format='iso8601')
        }

        app.logger.info("Getting list of all projects")
        projects = db.query_db(get_db(), 'select project_id, time_added from projects')

        marshaled_projects = []
        app.logger.debug("Getting list of all projects")
        for project_object in projects:
            marshaled_projects.append(marshal(project_object, project_resource_fields))

        return marshaled_projects

    @marshal_with(new_project_response_fields)
    def post(self):
        """Create a new project

        There are multiple result types, see documentation for how these effect information leakage
        and the resulting data.
        """
        data = get_json()

        try:
            project_model = models.Project.from_json(data)
        except models.InvalidProjectParametersException as e:
            safe_fail_request(400, message=e.msg)

        # Persist the new project
        app.logger.info("Adding new project to database")

        try:
            project_model.save(get_db())
        except Exception as e:
            app.logger.warn(e)
            safe_fail_request(500, 'Problem creating new project')

        return project_model, 201


class Project(Resource):

    def delete(self, project_id):
        # Check the resource exists
        abort_if_project_doesnt_exist(project_id)

        # Check the caller has a valid results token. Yes it should be renamed.
        abort_if_invalid_results_token(project_id, request.headers.get('Authorization'))

        dbinstance = get_db()
        mc = connect_to_object_store()
        project_from_db = db.get_project(dbinstance, project_id)

        app.logger.info("Deleting a project resource and all data")

        # If result_type is similarity_scores, delete the corresponding similarity_scores file
        if project_from_db['result_type'] == 'similarity_scores':
            app.logger.info("Deleting the similarity scores file")
            filename = db.get_similarity_scores_filename(dbinstance, project_id)['file']
            mc.remove_object(config.MINIO_BUCKET, filename)

        db.delete_project(get_db(), project_id)

        return '', 204

    def get(self, project_id):
        """
        This endpoint describes a Project.
        """
        app.logger.info("Getting detail for a project")
        abort_if_project_doesnt_exist(project_id)
        self.authorise_get_request(project_id)
        project_object = db.get_project(db.get_db(), project_id)

        # hack to rename parties -> number_parties
        project_object['number_parties'] = project_object['parties']
        del project_object['parties']

        project_description_fields = {
            'project_id': fields.String,
            'name': fields.String,
            'notes': fields.String,
            'schema': fields.Raw,
            'result_type': fields.String,
            'number_parties': fields.Integer
        }

        return marshal(project_object, project_description_fields)

    def authorise_get_request(self, resource_id):
        if request.headers is None or 'Authorization' not in request.headers:
            safe_fail_request(401, message="Authentication token required")
        auth_header = request.headers.get('Authorization')
        dp_id = None
        # Check the resource exists
        abort_if_project_doesnt_exist(resource_id)
        dbinstance = get_db()
        project_object = db.get_project(dbinstance, resource_id)
        app.logger.info("Checking credentials")
        if project_object['result_type'] == 'mapping' or project_object['result_type'] == 'similarity_scores':
            # Check the caller has a valid results token if we are including results
            abort_if_invalid_results_token(resource_id, auth_header)
        elif project_object['result_type'] == 'permutation':
            dp_id = dataprovider_id_if_authorize(resource_id, auth_header)
        elif project_object['result_type'] == 'permutation_unencrypted_mask':
            dp_id = node_id_if_authorize(resource_id, auth_header)
        else:
            safe_fail_request(500, "Unknown error")
        return dp_id, project_object


class ProjectClks(Resource):

    def post(self, project_id):
        """
        Update a project to provide data.
        """

        # Pass the request.stream to add_mapping_data
        # to avoid parsing the json in one hit, this enables running the
        # web frontend with less memory.
        headers = request.headers

        # Note we don't use request.stream so we handle chunked uploads without
        # the content length set...
        stream = get_stream()

        abort_if_project_doesnt_exist(project_id)
        if headers is None or 'Authorization' not in headers:
            safe_fail_request(401, message="Authentication token required")

        token = headers['Authorization']

        # Check the caller has valid token -> otherwise 403
        abort_if_invalid_dataprovider_token(token)

        dp_id = db.get_dataprovider_id(get_db(), token)

        app.logger.info("Receiving data for: dpid: {}".format(dp_id))
        receipt_token, raw_file = upload_clk_data(dp_id, stream)

        # Schedule a task to deserialize the hashes, and carry
        # out a pop count.
        handle_raw_upload.delay(project_id, dp_id, receipt_token)
        app.logger.info("Job scheduled to handle user uploaded hashes")

        return {'message': 'Updated', 'receipt-token': receipt_token}, 201


def upload_clk_data(dp_id, raw_stream):
    """
    Save the untrusted user provided data and start a celery job to
    deserialize, popcount and save the hashes.

    Because this takes place in a worker, we "lock" the upload by
    setting the state to pending in the bloomingdata table.
    """
    receipt_token = generate_code()

    filename = config.RAW_FILENAME_FMT.format(receipt_token)
    app.logger.info("Storing user {} supplied clks from json".format(dp_id))

    # We will increment a counter as we process
    store = {
        'count': 0,
        'totalbytes': 0
    }

    def counting_generator():
        try:
            for clk in ijson.items(raw_stream, 'clks.item'):
                # Often the clients upload base64 strings with newlines
                # We remove those here
                raw = ''.join(clk.split('\n')).encode() + b'\n'
                store['count'] += 1
                store['totalbytes'] += len(raw)
                yield raw
        except ijson.common.IncompleteJSONError as e:
            store['count'] = 0
            app.logger.warning("Stopping as we have received incomplete json")
            return

    # Annoyingly we need the totalbytes to upload to the object store
    # so we consume the input stream here. We could change the public
    # api instead so that we know the expected size ahead of time.
    data = b''.join(counting_generator())
    num_bytes = len(data)
    buffer = io.BytesIO(data)

    if store['count'] == 0:
        abort(400, message="Missing information")

    app.logger.info("Processed {} CLKS".format(store['count']))
    app.logger.info("Uploading {} to object store".format(fmt_bytes(num_bytes)))
    mc = connect_to_object_store()
    mc.put_object(
        config.MINIO_BUCKET,
        filename,
        data=buffer,
        length=len(data)
    )

    db.insert_filter_data(get_db(), filename, dp_id, receipt_token, store['count'])

    return receipt_token, filename