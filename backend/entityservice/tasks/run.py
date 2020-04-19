import psycopg2

from entityservice.cache import progress as progress_cache
from entityservice.cache.active_runs import set_run_state_active, is_run_missing
from entityservice.database import DBConn, check_project_exists, get_run, get_run_state_for_update
from entityservice.database import update_run_set_started
from entityservice.errors import RunDeleted, ProjectDeleted
from entityservice.tasks.base_task import TracedTask, run_failed_handler
from entityservice.tasks.comparing import create_comparison_jobs
from entityservice.async_worker import celery, logger


@celery.task(base=TracedTask, ignore_result=True, args_as_tags=('project_id', 'run_id'))
def prerun_check(project_id, run_id, parent_span=None):
    log = logger.bind(pid=project_id, run_id=run_id)
    log.debug("Sanity check that we need to compute run")

    # being very defensive here checking if the run state is already in the redis cache
    if not is_run_missing(run_id):
        log.warning("unexpectedly the run state is present in redis before starting")
        return

    with DBConn() as conn:
        if not check_project_exists(conn, project_id):
            log.debug("Project not found. Skipping")
            raise ProjectDeleted(project_id)

        res = get_run(conn, run_id)
        if res is None:
            log.debug(f"Run not found. Skipping")
            raise RunDeleted(run_id)

        try:
            db_state = get_run_state_for_update(conn, run_id)
        except psycopg2.OperationalError:
            log.warning("Run started in another task. Skipping this race.")
            return

        if db_state in {'running', 'completed', 'error'}:
            log.warning("Run already started. Skipping")
            return

        log.debug("Setting run state in db as 'running'")
        update_run_set_started(conn, run_id)

        log.debug("Updating redis cache for run")
        set_run_state_active(run_id)

    create_comparison_jobs.apply_async(
        kwargs={'project_id': project_id, 'run_id': run_id, 'parent_span': prerun_check.get_serialized_span()},
        link_error=run_failed_handler.s()
    )
    log.info("CLK similarity computation scheduled")
