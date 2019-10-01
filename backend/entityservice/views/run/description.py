import psycopg2
from flask import request
from structlog import get_logger
from tenacity import retry, wait_random_exponential, retry_if_exception_type, stop_after_delay

from entityservice import database as db
from entityservice.cache.active_runs import set_run_state_deleted
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


@retry(wait=wait_random_exponential(multiplier=1, max=60),
       retry=retry_if_exception_type(psycopg2.IntegrityError),
       stop=stop_after_delay(120))
def _delete_run(run_id, log):
    # Retry if a db integrity error occurs (e.g. when a worker is writing to the same row)
    # Randomly wait up to 2^x * 1 seconds between each retry until the range reaches 60 seconds, then randomly up to 60 seconds afterwards
    set_run_state_deleted(run_id)
    with db.DBConn() as conn:
        log.debug("Retrieving run details from database")
        similarity_file = get_similarity_file_for_run(conn, run_id)
        delete_run_data(conn, run_id)
    return similarity_file


def delete(project_id, run_id):
    log = logger.bind(pid=project_id, rid=run_id)
    log.debug("request to delete run")
    authorize_run_detail(project_id, run_id)
    log.debug("approved request to delete run")

    similarity_file = _delete_run(run_id, log)
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
