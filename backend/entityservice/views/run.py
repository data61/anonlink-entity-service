import io

import urllib3
from flask import Response, request
from flask_restful import Resource, fields, marshal

from entityservice import app, connect_to_object_store, iterable_to_stream, generate_scores
from entityservice.utils import safe_fail_request, generate_code
import entityservice.database as db
import entityservice.cache as cache
from entityservice.database import get_db, get_project_column
from entityservice.settings import Config as config
from entityservice.async_worker import check_queued_runs
from entityservice.views.auth_checks import abort_if_run_doesnt_exist, abort_if_project_doesnt_exist, abort_if_invalid_results_token


class Run(Resource):
    """

    """

    def get(self, project_id, run_id):

        app.logger.info("request description of a run")
        # Check the project and run resources exist
        abort_if_run_doesnt_exist(project_id, run_id)

        # Check the caller has a valid results token. Yes it should be renamed.
        abort_if_invalid_results_token(project_id, request.headers.get('Authorization'))

        app.logger.info("request for run description authorized")

        db_conn = db.get_db()
        run_object = db.get_run(db_conn, run_id)

        run_description_fields = {
            'run_id': fields.String,
            'threshold': fields.String,
            'notes': fields.String,
        }

        return marshal(run_object, run_description_fields)


class RunList(Resource):

    def post(self, project_id):

        app.logger.debug("Processing request to add a new run")
        # Check the resource exists
        abort_if_project_doesnt_exist(project_id)

        # Check the caller has a valid results token. Yes it should be renamed.
        abort_if_invalid_results_token(project_id, request.headers.get('Authorization'))

        data = request.get_json()

        threshold = data.get('threshold', config.ENTITY_MATCH_THRESHOLD)
        if threshold <= 0.0 or threshold >= 1.0:
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


class RunStatus(Resource):
    """
    Status of a particular run
    """

    def get(self, project_id, run_id):
        app.logger.info("request run status")
        # Check the project and run resources exist
        abort_if_run_doesnt_exist(project_id, run_id)

        # Check the caller has a valid results token. Yes it should be renamed.
        abort_if_invalid_results_token(project_id, request.headers.get('Authorization'))

        app.logger.info("request for run status authorized")
        dbinstance = get_db()
        is_ready, state = db.check_run_ready(dbinstance, run_id)

        # return compute time elapsed and number of comparisons here
        times = db.get_run_times(dbinstance, run_id)

        comparisons = cache.get_progress(run_id)
        total_comparisons = db.get_total_comparisons_for_project(dbinstance, project_id)

        progress = {
            'total': total_comparisons,
            'current': comparisons,
            'progress': (comparisons / total_comparisons) if total_comparisons is not 'NA' else 0.0
        }

        status = {
            "state": state,
            "message": "running",
            "progress": progress,
            "time_added": times['time_added']
        }

        if times['time_started'] is not None:
            status["time_started"] = times['time_started']

        if times['time_completed'] is not None:
            status["time_completed"] = times['time_completed']

        run_status_fields = {
            'state': fields.String,
            'message': fields.String,
            'progress': fields.Raw,
            'time_added': fields.DateTime(dt_format='iso8601'),
            'time_started': fields.DateTime(dt_format='iso8601'),
            'time_completed': fields.DateTime(dt_format='iso8601'),
        }

        return marshal(status, run_status_fields)


class RunResult(Resource):
    """
    Result of a particular run
    """

    def get(self, project_id, run_id):

        app.logger.info("Checking for results")

        # Check the project and run resources exist
        abort_if_run_doesnt_exist(project_id, run_id)

        # Check the caller has a valid results token.
        abort_if_invalid_results_token(project_id, request.headers.get('Authorization'))

        app.logger.info("request for run result authorized")

        dbinstance = get_db()
        is_ready, state = db.check_run_ready(dbinstance, run_id)

        # Check that the run is complete, otherwise 404
        if not is_ready:
            return 'run is not complete', 404

        result_type = get_project_column(dbinstance, project_id, 'result_type')
        run_object = db.get_run(dbinstance, run_id)

        if result_type == 'mapping':
            app.logger.info("Mapping result being returned")
            result = db.get_run_result(dbinstance, run_id)
            return {
                "mapping": result
            }

        elif result_type == 'permutation':
            app.logger.info("Encrypted permutation result being returned")
            return db.get_permutation_encrypted_result_with_mask(dbinstance, resource_id, dp_id)

        # elif run_object['result_type'] == 'permutation_unencrypted_mask':
        #     app.logger.info("Permutation with unencrypted mask result type")
        #
        #     if dp_id == "Coordinator":
        #         app.logger.info("Returning unencrypted mask to coordinator")
        #         # The mask is a json blob of an
        #         # array of 0/1 ints
        #         mask = db.get_permutation_unencrypted_mask(dbinstance, resource_id)
        #         return {
        #             "mask": mask
        #         }
        #     else:
        #         perm = db.get_permutation_result(dbinstance, dp_id)
        #         rows = db.get_smaller_dataset_size_for_project(dbinstance, resource_id)
        #
        #         return {
        #             'permutation': perm,
        #             'rows': rows
        #         }
        #     # The result in this case is either a permutation, or the encrypted mask.
        #     # The key 'permutation_unencrypted_mask' is kept for the Java recognition of the algorithm.
        #
        # elif mapping['result_type'] == 'similarity_scores':
        #     app.logger.info("Similarity scores being returned")
        #
        #     try:
        #         filename = db.get_similarity_scores_filename(dbinstance, resource_id)['file']
        #         return get_similarity_scores(filename)
        #
        #     except TypeError:
        #         app.logger.warning("`resource_id` is valid but it is not in the similarity scores table.")
        #         safe_fail_request(500, "Fail to retrieve similarity scores")

        else:
            app.logger.warning("Unimplemented result type")


def get_similarity_scores(filename):
    """
    Read a CSV file containing the similarity scores and return the similarity scores

    :param filename: name of the CSV file, obtained from the `similarity_scores` table
    :return: the similarity scores in a streaming JSON response.
    """

    mc = connect_to_object_store()

    try:
        csv_data_stream = iterable_to_stream(mc.get_object(config.MINIO_BUCKET, filename).stream())

        # Process the CSV into JSON
        csv_text_stream = io.TextIOWrapper(csv_data_stream, encoding="utf-8")

        return Response(generate_scores(csv_text_stream), mimetype='application/json')

    except urllib3.exceptions.ResponseError:
        app.logger.warning("Attempt to read the similarity scores file failed with an error response.")
        safe_fail_request(500, "Failed to retrieve similarity scores")