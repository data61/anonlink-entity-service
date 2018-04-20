import io

import urllib3
from flask import Response
from flask_restful import Resource, fields, marshal

from entityservice import app, connect_to_object_store, iterable_to_stream, generate_scores
from entityservice.utils import safe_fail_request
import entityservice.database as db
from entityservice.database import get_db
from entityservice.settings import Config as config


class Run(Resource):
    """

    """

    def post(self):

        #TODO
        raise NotImplementedError
        threshold = data.get('threshold', config.ENTITY_MATCH_THRESHOLD)
        if threshold <= 0.0 or threshold >= 1.0:
            safe_fail_request(400, message="Threshold parameter out of range")

        app.logger.debug("Threshold for mapping is {}".format(threshold))


class RunList(Resource):

    def get(self):
        return []


class RunStatus(Resource):
    """
    Status of a particular run
    """

    def get(self, resource_id):

        is_ready, state = db.check_run_ready(get_db(), resource_id)

        return 'TODO'


class RunResult(Resource):
    """
    Result of a particular run
    """

    def get(self, resource_id):
        # TODO
        raise NotImplementedError

        app.logger.info("Checking for results")
        dbinstance = get_db()

        # Check that the mapping is ready
        if not mapping['ready']:
            progress = self.get_mapping_progress(dbinstance, resource_id)
            return progress, 503

        if mapping['result_type'] == 'mapping':
            app.logger.info("Mapping result being returned")
            result = db.get_run_result(dbinstance, resource_id)
            return {
                "mapping": result
            }

        elif mapping['result_type'] == 'permutation':
            app.logger.info("Encrypted permutation result being returned")
            return db.get_permutation_encrypted_result_with_mask(dbinstance, resource_id, dp_id)

        elif mapping['result_type'] == 'permutation_unencrypted_mask':
            app.logger.info("Permutation with unencrypted mask result type")

            if dp_id == "Coordinator":
                app.logger.info("Returning unencrypted mask to coordinator")
                # The mask is a json blob of an
                # array of 0/1 ints
                mask = db.get_permutation_unencrypted_mask(dbinstance, resource_id)
                return {
                    "mask": mask
                }
            else:
                perm = db.get_permutation_result(dbinstance, dp_id)
                rows = db.get_smaller_dataset_size_for_project(dbinstance, resource_id)

                return {
                    'permutation': perm,
                    'rows': rows
                }
            # The result in this case is either a permutation, or the encrypted mask.
            # The key 'permutation_unencrypted_mask' is kept for the Java recognition of the algorithm.

        elif mapping['result_type'] == 'similarity_scores':
            app.logger.info("Similarity scores being returned")

            try:
                filename = db.get_similarity_scores_filename(dbinstance, resource_id)['file']
                return get_similarity_scores(filename)

            except TypeError:
                app.logger.warning("`resource_id` is valid but it is not in the similarity scores table.")
                safe_fail_request(500, "Fail to retrieve similarity scores")

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