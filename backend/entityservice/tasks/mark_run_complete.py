from entityservice.async_worker import celery, logger
from entityservice.cache.active_runs import set_run_state_complete
from entityservice.database import DBConn, update_run_mark_complete
from entityservice.tasks import TracedTask


@celery.task(base=TracedTask, ignore_results=True, args_as_tags=('run_id',))
def mark_run_complete(run_id, parent_span=None):
    log = logger.bind(run_id=run_id)
    log.debug("Marking run complete")
    with DBConn() as db:
        update_run_mark_complete(db, run_id)
    set_run_state_complete(run_id)
    log.info("Run marked as complete")
