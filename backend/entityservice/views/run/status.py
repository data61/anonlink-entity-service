from flask import request, g
from structlog import get_logger
import opentracing

from entityservice.cache import progress as progress_cache
from entityservice import database as db
from entityservice.views import bind_log_and_span
from entityservice.views.auth_checks import abort_if_run_doesnt_exist, get_authorization_token_type_or_abort
from entityservice.views.serialization import completed, running, error
from entityservice.models.run import RUN_TYPES

logger = get_logger()


def get(project_id, run_id):
    log, parent_span = bind_log_and_span(project_id, run_id)
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
        abs_val = progress_cache.get_comparison_count_for_run(run_id)
        if abs_val is not None:
            max_val = progress_cache.get_total_number_of_comparisons(project_id)
            logger.debug(f"total comparisons: {max_val}")
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
        status["total_number_comparisons"] = progress_cache.get_total_number_of_comparisons(project_id)
        return completed().dump(status)
    elif state == 'running' or state == 'queued' or state == 'created':
        status["time_started"] = run_status['time_started']
        return running().dump(status)
    elif state == 'error':
        status['message'] = run_status['error_msg']
        return error().dump(status)
