from flask import request
from flask_restful import Resource

from entityservice import app, database as db
from entityservice.database import get_db, get_project_column
from entityservice.serialization import get_similarity_scores
from entityservice.utils import safe_fail_request
from entityservice.views import abort_if_invalid_results_token
from entityservice.views.auth_checks import abort_if_run_doesnt_exist


class RunResult(Resource):
    """
    Result of a particular run
    """

    def get(self, project_id, run_id):

        app.logger.info("Checking for results of run {}".format(run_id))

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

        if result_type == 'mapping':
            app.logger.info("Mapping result being returned")
            result = db.get_run_result(dbinstance, run_id)
            return {
                "mapping": result
            }

        elif result_type == 'similarity_scores':
            app.logger.info("Similarity score result being returned")

            try:
                filename = db.get_similarity_scores_filename(dbinstance, run_id)
                return get_similarity_scores(filename)

            except TypeError:
                app.logger.warning("Couldn't find the similarity score file")
                safe_fail_request(500, "Failed to retrieve similarity scores")

        # TODO permutation result type
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

        else:
            app.logger.warning("Unimplemented result type")