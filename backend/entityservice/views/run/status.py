from flask import request, g
from structlog import get_logger
import opentracing

from entityservice import database as db, cache as cache
from entityservice.metrics import RUN_STATUS_COUNT
from entityservice.views.auth_checks import abort_if_run_doesnt_exist, get_authorization_token_type_or_abort
from entityservice.views.serialization import completed, running, error
from entityservice.models.run import RUN_TYPES

logger = get_logger()


def get(project_id, run_id):
    log = logger.bind(pid=project_id,rid=run_id)
    parent_span = g.flask_tracer.get_span()
    log.debug("request run status")
    with opentracing.tracer.start_span('check-auth', child_of=parent_span) as span:
        # Check the project and run resources exist
        abort_if_run_doesnt_exist(project_id, run_id)

        # Check the caller has a valid results token. Yes it should be renamed.
        auth_token_type = get_authorization_token_type_or_abort(project_id, request.headers.get('Authorization'))
        log.debug("Run status authorized using {} token".format(auth_token_type))

    with opentracing.tracer.start_span('get-status-from-db', child_of=parent_span) as span:
        with db.DBConn() as conn:
            run_status = db.get_run_status(conn, run_id)
            project_in_error = db.get_encoding_error_count(conn, project_id) > 0
        span.set_tag('stage', run_status['stage'])
    RUN_STATUS_COUNT.labels(run=run_id).inc()
    run_type = RUN_TYPES[run_status['type']]
    state = 'error' if project_in_error else run_status['state']
    stage = run_status['stage']
    status = {
        "state": state,
        "time_added": run_status['time_added'],
        "stages": run_type['stages'],
        "current_stage": {
            "number": stage,
            "description": run_type['stage_descriptions'].get(stage, "there is no description for this stage")
        }
    }
    # trying to get progress if available
    if stage == 1:
        # waiting for CLKs
        with db.DBConn() as conn:
            abs_val = db.get_number_parties_uploaded(conn, project_id)
            max_val = db.get_project_column(conn, project_id, 'parties')
    elif stage == 2:
        # Computing similarity
        abs_val = cache.get_progress(run_id)
        if abs_val is not None:
            with db.DBConn() as conn:
                max_val = db.get_total_comparisons_for_project(conn, project_id)
    else:
        # Solving for mapping (no progress)
        abs_val = None
    if abs_val is not None:
        progress = {
            'absolute': abs_val,
            'relative': (abs_val / max_val) if max_val != 0 else 0,
        }
        if progress['relative'] > 1.0:
            log.warning('oh no. more than 100% ??? abs: {}, max: {}'.format(abs_val, max_val))
        if run_status['stage'] in run_type['stage_progress_descriptions']:
            progress['description'] = run_type['stage_progress_descriptions'][run_status['stage']]
        status["current_stage"]["progress"] = progress
    if state == 'completed':
        status["time_started"] = run_status['time_started']
        status["time_completed"] = run_status['time_completed']
        return completed().dump(status)
    elif state == 'running' or state == 'queued' or state == 'created':
        status["time_started"] = run_status['time_started']
        return running().dump(status)
    elif state == 'error':
        log.warning('handling the run status for state "error" is not implemented')
        return error().dump(status)
