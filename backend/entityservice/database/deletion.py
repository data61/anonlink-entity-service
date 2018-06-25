from entityservice.database.util import query_db, execute_returning_id, logger
from entityservice.database.selections import get_project, get_all_objects_for_project


def delete_project(db, project_id):
    """
    Deletes the database entries for a particular project and returns
    a list of object store files referenced.

    This is very manual, looking forward to https://github.com/n1analytics/entity-service/issues/133
    """
    project = get_project(db, project_id)
    result_type = project['result_type']

    object_store_files = get_all_objects_for_project(db, project_id)

    with db.cursor() as cur:
        logger.info("Beginning db transaction to remove everything associated with project")
        cur.execute("""
            DELETE FROM projects
            WHERE project_id = %s
            """, [project_id])

    logger.info("Committing removal of mapping resource")
    db.commit()
    return object_store_files
