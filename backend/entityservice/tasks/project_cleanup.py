from minio.error import MinioError

from entityservice.object_store import connect_to_object_store
from entityservice.async_worker import celery, logger
from entityservice.tasks.base_task import TracedTask
from entityservice.settings import Config as config


@celery.task(base=TracedTask, ignore_result=True, args_as_tags=('project_id',))
def remove_project(project_id):
    """

    """
    log = logger.bind(pid=project_id)
    log.info("Removing all resources associated with a project")

    # with db.DBConn() as conn:
    #     log.info("Deleting project resourced from database")
    #     object_store_files = db.get_all_objects_for_project(conn, project_id)
    #     #log.info("Removing project")
    #     #db.delete_project(conn, project_id)
    # log.info("Removing object store files associated with project.")
    # delete_minio_objects.delay(object_store_files, project_id)

    log.info("Project resources removed")


@celery.task(base=TracedTask, ignore_result=True, args_as_tags=('project_id',))
def delete_minio_objects(filenames, project_id):
    log = logger.bind(pid=project_id)
    mc = connect_to_object_store()
    log.info(f"Deleting {len(filenames)} files from object store")
    try:
        mc.remove_objects(config.MINIO_BUCKET, filenames)
    except MinioError as e:
        log.warning(f"Error occurred while removing object {filename}. Ignoring.")
