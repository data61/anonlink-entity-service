from entityservice.database import DBConn, logger, \
    check_project_exists, get_run, update_run_set_started, get_dataprovider_ids
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
            log.info("Project not found. Skipping")
            raise ProjectDeleted(project_id)

        res = get_run(conn, run_id)
        if res is None:
            log.info(f"Run not found. Skipping")
            raise RunDeleted(run_id)

        if res['state'] in {'completed', 'error'}:
            log.info("Run is already finished. Skipping")
            return
        if res['state'] == 'running':
            log.info("Run already started. Skipping")
            return

        log.debug("Setting run as in progress")
        update_run_set_started(conn, run_id)

        log.debug("Getting dp ids for compute similarity task")
        dp_ids = get_dataprovider_ids(conn, project_id)
        log.debug("Data providers: {}".format(dp_ids))
        if len(dp_ids) != 2:
            log.warning(f"Only support two party comparisons at the moment. Got {len(dp_ids)}")
            return

    create_comparison_jobs.delay(project_id, run_id, prerun_check.get_serialized_span())
    log.info("CLK similarity computation scheduled")
