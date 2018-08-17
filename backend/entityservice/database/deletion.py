from entityservice.database.util import query_db, execute_returning_id
from entityservice.database.selections import get_project, get_all_objects_for_project
from structlog import get_logger

logger = get_logger()


def delete_project(db, project_id):
    """
    Deletes the database entry for a particular project.

    This is very manual, looking forward to https://github.com/n1analytics/entity-service/issues/133
    """
    object_store_files = get_all_objects_for_project(db, project_id)

    with db.cursor() as cur:
        logger.warning("Beginning db transaction to remove everything associated with project")
        cur.execute("""
            DELETE FROM projects
            WHERE project_id = %s
            """, [project_id])

    logger.info("Committing removal of project resource")
    db.commit()
    return object_store_files
