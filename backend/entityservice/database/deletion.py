from entityservice.database.util import query_db, execute_returning_id, logger
from entityservice.database.selections import get_project


def delete_project(db, project_id):
    """
    Deletes the database entries for a particular project and returns
    a list of object store files referenced.


    This is very manual, looking forward to https://github.com/n1analytics/entity-service/issues/133
    """
    project = get_project(db, project_id)
    result_type = project['result_type']

    object_store_files = []

    with db.cursor() as cur:
        logger.info("Beginning db transaction to remove everything associated with project")
        dps = query_db(db, """
            SELECT id
            FROM dataproviders
            WHERE project = %s
            """, [project_id])

        for dp in dps:
            clk_file_ref = execute_returning_id(cur, """
                DELETE FROM bloomingdata
                WHERE dp = %s
                RETURNING file
                """, [dp['id']])
            if clk_file_ref is not None:
                logger.info("blooming data file found: {}".format(clk_file_ref))
                object_store_files.append(clk_file_ref)

            if result_type != 'mapping':
                # All views except mapping have a permutation entry per dp per run:
                cur.execute("""
                    DELETE FROM permutations
                    WHERE dp = %s
                    """, [dp['id']])

        if result_type != 'mapping':
            # # All views except mapping have a permutation mask per run:
            cur.execute("""
                DELETE FROM permutation_masks
                WHERE project = %s
                """, [project_id])

        if result_type == "similarity_scores":
            cur.execute("""
                DELETE FROM similarity_scores
                USING runs 
                WHERE 
                  runs.run_id = similarity_scores.run AND
                  runs.project = %s
                RETURNING similarity_scores.file
                """, [project_id])
            query_response = cur.fetchall()
            if query_response is not None:
                similarity_files = [res[0] for res in query_response]
                object_store_files.extend(similarity_files)

        cur.execute("""
            DELETE FROM dataproviders
            WHERE project = %s
            """, [project_id])

        cur.execute("""
            DELETE FROM run_results
            USING runs
            WHERE 
              runs.run_id = run_results.run AND
              runs.project = %s
            """, [project_id])

        cur.execute("""
            DELETE FROM runs
            WHERE project = %s
            """, [project_id])

        cur.execute("""
            DELETE FROM projects
            WHERE project_id = %s
            """, [project_id])

    logger.info("Committing removal of mapping resource")
    db.commit()
    return object_store_files