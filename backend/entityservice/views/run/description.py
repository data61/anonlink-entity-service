from flask import request
from flask_restful import fields, marshal

from entityservice import app, database as db
from entityservice.views.auth_checks import abort_if_run_doesnt_exist, abort_if_invalid_results_token


def get(project_id, run_id):
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
        'threshold': fields.Float,
        'notes': fields.String,
    }

    return marshal(run_object, run_description_fields)


def delete(project_id, run_id):
    app.logger.warn("delete on runs is not implemented! Help!")
