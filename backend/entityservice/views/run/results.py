from flask import request
from flask_restful import Resource

from entityservice import app, database as db
from entityservice.database import get_db, get_project_column
from entityservice.serialization import get_similarity_scores
from entityservice.utils import safe_fail_request
from entityservice.views import abort_if_invalid_results_token
from entityservice.views.auth_checks import abort_if_run_doesnt_exist, get_authorization_token_type_or_abort


class RunResult(Resource):
    """
    Result of a particular run
    """

    def get(self, project_id, run_id):

        app.logger.info("Checking for results of run {}".format(run_id))

        # Check the project and run resources exist
        abort_if_run_doesnt_exist(project_id, run_id)

        # Check the caller has a valid results token.
        token = request.headers.get('Authorization')
        auth_token_type = get_authorization_token_type_or_abort(project_id, token)
        app.logger.info("request to access run result authorized")
        dbinstance = get_db()

        is_ready, state = db.check_run_ready(dbinstance, run_id)

        # Check that the run is complete, otherwise 404
        if not is_ready:
            return 'run is not complete', 404

        result_type = get_project_column(dbinstance, project_id, 'result_type')

        if result_type == 'mapping':
            app.logger.info("Mapping result being returned")
            result = db.get_run_result(dbinstance, run_id)
            return {"mapping": result}

        elif result_type == 'similarity_scores':
            return self.get_similarity_score_result(dbinstance, run_id)

        elif result_type == 'permutation_unencrypted_mask':
            return self.get_permutation_unencrypted_result(project_id, run_id, dbinstance, token, auth_token_type)

        else:
            app.logger.warning("Unimplemented result type")

    def get_similarity_score_result(self, dbinstance, run_id):
        app.logger.info("Similarity score result being returned")
        try:
            filename = db.get_similarity_scores_filename(dbinstance, run_id)
            return get_similarity_scores(filename)

        except TypeError:
            app.logger.warning("Couldn't find the similarity score file")
            safe_fail_request(500, "Failed to retrieve similarity scores")

    def get_permutation_unencrypted_result(self, project_id, run_id, dbinstance, token, auth_token_type):
        app.logger.info("Permutation with unencrypted mask result type being returned")
        if auth_token_type == 'receipt_token':
            dp_id = db.select_dataprovider_id(dbinstance, project_id, token)
            perm = db.get_permutation_result(dbinstance, dp_id, run_id)
            rows = db.get_smaller_dataset_size_for_project(dbinstance, project_id)
            result = {
                'permutation': perm,
                'rows': rows
            }
        elif auth_token_type == "result_token":
            app.logger.info("Returning unencrypted mask to coordinator")
            # The mask is a json blob of an
            # array of 0/1 ints
            mask = db.get_permutation_unencrypted_mask(dbinstance, project_id, run_id)
            result = {
                "mask": mask
            }
        else:
            app.logger.warning("Didn't recognize the auth token type of {}".format(auth_token_type))
            safe_fail_request(500, "Unknown error. Please report to the developers")
        return result