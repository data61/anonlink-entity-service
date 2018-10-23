from flask import request
from structlog import get_logger
from entityservice import database as db
from entityservice.views.auth_checks import abort_if_run_doesnt_exist, abort_if_invalid_results_token
from entityservice.views.serialization import RunDescription

logger = get_logger()


def get(project_id, run_id):
    log = logger.bind(pid=project_id, rid=run_id)
    logger.info("request description of a run")
    # Check the project and run resources exist
    abort_if_run_doesnt_exist(project_id, run_id)

    # Check the caller has a valid results token. Yes it should be renamed.
    abort_if_invalid_results_token(project_id, request.headers.get('Authorization'))

    log.info("request for run description authorized")

    db_conn = db.get_db()
    run_object = db.get_run(db_conn, run_id)

    return RunDescription().dump(run_object)


def delete(project_id, run_id):
    log = logger.bind(pid=project_id, rid=run_id)
    log.warn("delete on runs is not implemented! Help!")
