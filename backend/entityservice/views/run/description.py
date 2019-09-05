import psycopg2
from flask import request
from structlog import get_logger

from entityservice import database as db
from entityservice.database import delete_run_data, get_similarity_file_for_run
from entityservice.views.auth_checks import abort_if_run_doesnt_exist, abort_if_invalid_results_token
from entityservice.views.serialization import RunDescription
from entityservice.tasks import delete_minio_objects

logger = get_logger()


def get(project_id, run_id):
    log = logger.bind(pid=project_id, rid=run_id)
    log.info("request description of a run")
    authorize_run_detail(project_id, run_id)
    log.debug("request for run description authorized")

    with db.DBConn() as conn:
        log.debug("Retrieving run description from database")
        run_object = db.get_run(conn, run_id)

    return RunDescription().dump(run_object)


def delete(project_id, run_id):
    log = logger.bind(pid=project_id, rid=run_id)
    log.debug("request to delete run")
    authorize_run_detail(project_id, run_id)
    log.debug("approved request to delete run")

    try:
        with db.DBConn() as conn:
            log.debug("Retrieving run details from database")
            similarity_file = get_similarity_file_for_run(conn, run_id)
            delete_run_data(conn, run_id)
    except psycopg2.IntegrityError as e:
        log.warning("Failed to delete run")
        log.exception(e)
    log.debug("Deleted run from database")

    if similarity_file:
        log.debug("Queuing task to remove similarities file from object store")
        delete_minio_objects.delay([similarity_file], project_id)
    return '', 204


def authorize_run_detail(project_id, run_id):
    # Check the project and run resources exist
    abort_if_run_doesnt_exist(project_id, run_id)
    # Check the caller has a valid results token. Yes it should be renamed.
    abort_if_invalid_results_token(project_id, request.headers.get('Authorization'))
