from entityservice.cache.active_runs import is_run_active
from entityservice.database import DBConn, check_project_exists, check_run_exists
from entityservice.errors import DBResourceMissing, InactiveRun


def assert_valid_run(project_id, run_id, log):
    if not is_run_active(run_id):
        raise InactiveRun("Run isn't marked as active")

    with DBConn() as db:
        if not check_project_exists(db, project_id) or not check_run_exists(db, project_id, run_id):
            log.info("Project or run not found in database.")
            raise DBResourceMissing("project or run not found in database")
