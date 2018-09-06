
import entityservice.database as db
from entityservice import connect_to_object_store
from entityservice.tasks.base_task import BaseTask
from entityservice.settings import Config as config

import structlog
import celery
import logging

logger = structlog.wrap_logger(logging.getLogger('celery'))


@celery.task(base=BaseTask, ignore_result=True)
def delete_project(project_id):
    """

    """
    log = logger.bind(pid=project_id)
    log.info("Removing all resources associated with a project")

    with db.DBConn() as conn:
        log.info("Removing project")

        mc = connect_to_object_store()

        log.info("Deleting project resourced from database")
        object_store_files = db.delete_project(conn, project_id)
        log.info("Removing object store files associated with project.")

        for filename in object_store_files:
            log.info("Deleting {}".format(filename))
            mc.remove_object(config.MINIO_BUCKET, filename)

    log.info("Project resources removed")

