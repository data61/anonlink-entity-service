from flask import g
from structlog import get_logger

logger = get_logger()


def bind_log_and_span(project_id, run_id=None):

    log = logger.bind(pid=project_id)
    parent_span = g.flask_tracer.get_span()
    parent_span.set_tag("project_id", project_id)
    if run_id is not None:
        log = log.bind(rid=run_id)
        parent_span.set_tag("run_id", run_id)
    return log, parent_span
