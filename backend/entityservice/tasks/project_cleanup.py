from minio.deleteobjects import DeleteObject
from minio.error import MinioException

import entityservice.database as db
from entityservice.cache.active_runs import set_run_state_deleted
from entityservice.database import DBConn
from entityservice.object_store import connect_to_object_store, delete_object_store_folder
from entityservice.async_worker import celery, logger
from entityservice.tasks.base_task import TracedTask
from entityservice.settings import Config


@celery.task(base=TracedTask,
             ignore_result=True,
             args_as_tags=('project_id',))
def remove_project(project_id, parent_span=None):
    """

    """
    log = logger.bind(pid=project_id)
    log.debug("Remove all project resources")

    with DBConn() as conn:
        run_objects = db.get_runs(conn, project_id)
        log.debug("Setting run status as 'deleted'")
        for run in run_objects:
            set_run_state_deleted(run_id=run['run_id'])
        log.debug("Deleting project resourced from database")
        db.delete_project_data(conn, project_id)
        log.debug("Getting object store files associated with project from database")
        object_store_files = db.get_all_objects_for_project(conn, project_id)

    delete_minio_objects.delay(object_store_files, project_id, parent_span)
    log.info("Project resources removed")


@celery.task(base=TracedTask,
             ignore_result=True,
             args_as_tags=('project_id',))
def delete_minio_objects(filenames, project_id, parent_span=None):
    log = logger.bind(pid=project_id)
    mc = connect_to_object_store()
    log.info(f"Deleting {len(filenames)} files from object store")
    delete_objects = [DeleteObject(f) for f in filenames]
    try:
        for del_err in mc.remove_objects(Config.MINIO_BUCKET, delete_objects):
            log.debug("Deletion error: {}".format(del_err))
    except MinioException as e:
        log.warning(f"Error occurred while removing object {filenames}. Ignoring.")

    if Config.UPLOAD_OBJECT_STORE_ENABLED:
        log.debug("Deleting everything uploaded to object store for project")
        try:
            delete_object_store_folder(mc, Config.UPLOAD_OBJECT_STORE_BUCKET, f"{project_id}/")
        except MinioException as e:
            log.warning(f"Error occurred while trying to remove files from object store upload bucket: {e}")
