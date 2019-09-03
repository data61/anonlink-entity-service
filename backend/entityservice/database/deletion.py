from structlog import get_logger

logger = get_logger()


def delete_run_data(conn, run_id):
    """
    Deletes a run and all associated results.
    """
    with conn:
        logger.debug("start db transaction to delete run")
        with conn.cursor() as cur:
            # Note, data in tables
            # run_results, similarity_scores, permutations
            # and permutation_masks should delete their rows when
            # runs row is deleted due to "on DELETE CASCADE"
            cur.execute("""
                DELETE
                FROM runs
                WHERE
                    run_id = %s
                """, [run_id])
        logger.debug("Finishing DB transaction to delete run")
    logger.info("Run resources removed")


def delete_project_data(conn, project_id):
    """
    Deletes the mappings and permutations for a given project.

    This is very manual, looking forward to https://github.com/n1analytics/entity-service/issues/133
    """
    # Note the first context manager begins a database transaction
    with conn:
        with conn.cursor() as cur:
            logger.debug("Beginning db transaction to remove result data associated with project")
            cur.execute("""
                DELETE
                FROM run_results
                  USING runs
                WHERE
                    runs.run_id = run_results.run AND
                    runs.project = %s
                """, [project_id])

            cur.execute("""
                DELETE
                FROM permutations
                  USING runs
                WHERE
                    runs.run_id = permutations.run AND
                    runs.project =  %s
                """, [project_id])

            cur.execute("""
                DELETE
                FROM permutation_masks
                WHERE
                    permutation_masks.project =  %s
                """, [project_id])

        logger.debug("Committing removal of project resource")

