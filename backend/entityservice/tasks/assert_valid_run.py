from entityservice.database import DBConn, check_project_exists, check_run_exists
from entityservice.errors import DBResourceMissing


def assert_valid_run(project_id, run_id, log):
    with DBConn() as db:
        if not check_project_exists(db, project_id) or not check_run_exists(db, project_id, run_id):
            log.info("Project or run not found in database.")
            raise DBResourceMissing("project or run not found in database")
