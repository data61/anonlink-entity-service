import psycopg2

from entityservice.cache import progress as progress_cache
from entityservice.database import DBConn, check_project_exists, get_run, get_run_state_for_update
from entityservice.database import update_run_set_started, get_dataprovider_ids
from entityservice.errors import RunDeleted, ProjectDeleted
from entityservice.tasks.base_task import TracedTask
from entityservice.tasks.comparing import create_comparison_jobs
from entityservice.async_worker import celery, logger


@celery.task(base=TracedTask, ignore_result=True, args_as_tags=('project_id', 'run_id'))
def prerun_check(project_id, run_id, parent_span=None):
    log = logger.bind(pid=project_id, run_id=run_id)
    log.debug("Sanity check that we need to compute run")

    with DBConn() as conn:
        if not check_project_exists(conn, project_id):
            log.debug("Project not found. Skipping")
            raise ProjectDeleted(project_id)

        res = get_run(conn, run_id)
        if res is None:
            log.debug(f"Run not found. Skipping")
            raise RunDeleted(run_id)

        try:
            state = get_run_state_for_update(conn, run_id)
        except psycopg2.OperationalError:
            log.warning("Run started in another task. Skipping this race.")
            return

        if state in {'running', 'completed', 'error'}:
            log.warning("Run already started. Skipping")
            return

        log.debug("Setting run as in progress")
        update_run_set_started(conn, run_id)
        progress_cache.save_current_progress(comparisons=0, run_id=run_id)

        log.debug("Getting dp ids for compute similarity task")
        dp_ids = get_dataprovider_ids(conn, project_id)
        log.debug("Data providers: {}".format(dp_ids))

    create_comparison_jobs.delay(project_id, run_id, prerun_check.get_serialized_span())
    log.info("CLK similarity computation scheduled")
