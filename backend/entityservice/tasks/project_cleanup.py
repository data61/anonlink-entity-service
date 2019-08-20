from minio.error import MinioError

import entityservice.database as db
from entityservice.database import DBConn
from entityservice.object_store import connect_to_object_store
from entityservice.async_worker import celery, logger
from entityservice.tasks.base_task import TracedTask
from entityservice.settings import Config


@celery.task(base=TracedTask,
             ignore_result=True,
             args_as_tags=('project_id',))
def remove_project(project_id):
    """

    """
    log = logger.bind(pid=project_id)
    log.debug("Remove all project resources")

    with DBConn() as conn:
        #conn = db.connect_db()
        log.debug("Deleting project resourced from database")
        db.delete_project_data(conn, project_id)
        log.debug("Getting object store files associated with project from database")
        object_store_files = db.get_all_objects_for_project(conn, project_id)
        log.debug(f"Removing {len(object_store_files)} object store files associated with project.")
        delete_minio_objects.delay(object_store_files, project_id)
        log.info("Project resources removed")


@celery.task(base=TracedTask,
             ignore_result=True,
             args_as_tags=('project_id',))
def delete_minio_objects(filenames, project_id):
    log = logger.bind(pid=project_id)
    mc = connect_to_object_store()
    log.info(f"Deleting {len(filenames)} files from object store")
    try:
        mc.remove_objects(Config.MINIO_BUCKET, filenames)
    except MinioError as e:
        log.warning(f"Error occurred while removing object {filenames}. Ignoring.")
