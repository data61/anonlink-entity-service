from flask import request
from flask_restful import Resource, fields, marshal

from entityservice import app, database as db
from entityservice.async_worker import check_queued_runs
from entityservice.database import get_db
from entityservice.settings import Config as config
from entityservice.utils import safe_fail_request, generate_code
from entityservice.views import abort_if_project_doesnt_exist, abort_if_invalid_results_token


class RunList(Resource):

    def post(self, project_id):

        app.logger.debug("Processing request to add a new run")
        # Check the resource exists
        abort_if_project_doesnt_exist(project_id)

        # Check the caller has a valid results token. Yes it should be renamed.
        abort_if_invalid_results_token(project_id, request.headers.get('Authorization'))

        data = request.get_json()

        threshold = data.get('threshold', config.ENTITY_MATCH_THRESHOLD)
        if threshold <= 0.0 or threshold > 1.0:
            safe_fail_request(400, message="Threshold parameter out of range")
        app.logger.info("Threshold for run is: {}".format(threshold))

        notes = data.get("notes", '')
        run_id = generate_code()
        app.logger.debug("Inserting run into database")

        db_conn = db.get_db()
        db.insert_new_run(db_conn, run_id, project_id, threshold, notes)

        project_object = db.get_project(db_conn, project_id)
        parties_contributed = db.get_number_parties_uploaded(db_conn, project_id)

        if parties_contributed == project_object['parties']:
            app.logger.info("Scheduling task to carry out the run now")
            check_queued_runs.delay(project_id)
        else:
            app.logger.info("Task queued but won't start until CLKs are all uploaded")
        return {
            'run_id': run_id,
        }, 201

    def get(self, project_id,):
        app.logger.info("Listing runs for project: {}".format(project_id))

        self.authorize_run_listing(project_id)

        app.logger.info("Authorized request to list runs")

        select_query = '''
          SELECT run_id, time_added, state 
          FROM runs
          WHERE
            project = %s
        '''
        runs = db.query_db(get_db(), select_query, (project_id,))

        run_summary_fields = {
            'run_id': fields.String,
            'time_added': fields.DateTime(dt_format='iso8601'),
            'state': fields.String
        }

        marshaled_runs = []
        app.logger.debug("Marshaling list of all projects")
        for run_object in runs:
            marshaled_runs.append(marshal(run_object, run_summary_fields))

        return marshaled_runs

    def authorize_run_listing(self, project_id):
        app.logger.info("Looking up project")
        abort_if_project_doesnt_exist(project_id)
        if request.headers is None or 'Authorization' not in request.headers:
            safe_fail_request(401, message="Authentication token required")
        auth_header = request.headers.get('Authorization')
        # Check the project resource exists
        abort_if_project_doesnt_exist(project_id)
        dbinstance = get_db()
        project_object = db.get_project(dbinstance, project_id)
        app.logger.info("Checking credentials to list project runs")
        # Check the caller has a valid results token (analyst token)
        abort_if_invalid_results_token(project_id, auth_header)
        app.logger.info("Caller is allowed to list project runs")