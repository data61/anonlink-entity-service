import logging

from minio.error import MinioError
import structlog
import celery

import entityservice.database as db
from entityservice import connect_to_object_store
from entityservice.tasks.base_task import TracedTask
from entityservice.settings import Config as config


logger = structlog.wrap_logger(logging.getLogger('celery'))


@celery.task(base=TracedTask, ignore_result=True, args_as_tags=('project_id',))
def delete_project(project_id):
    """

    """
    log = logger.bind(pid=project_id)
    log.info("Removing all resources associated with a project")

    with db.DBConn() as conn:
        log.info("Removing project")
        log.info("Deleting project resourced from database")
        object_store_files = db.delete_project(conn, project_id)
    log.info("Removing object store files associated with project.")
    delete_minio_objects.delay(object_store_files, project_id)

    log.info("Project resources queued for removal")


@celery.task(base=TracedTask, ignore_result=True, args_as_tags=('project_id',))
def delete_minio_objects(filenames, project_id):
    log = logger.bind(pid=project_id)
    mc = connect_to_object_store()
    log.info(f"Deleting {len(filenames)} files from object store")
    try:
        mc.remove_objects(config.MINIO_BUCKET, filenames)
    except MinioError as e:
        log.warning(f"Error occurred while removing object {filename}. Ignoring.")
