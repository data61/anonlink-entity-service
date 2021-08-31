from structlog import get_logger

from entityservice.database import get_dataprovider_ids

logger = get_logger()


def delete_run_data(conn, run_id):
    """
    Deletes a run and all associated results.
    """
    log = logger.bind(rid=run_id)
    with conn:
        log.debug("start db transaction to delete run")
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
        log.debug("Finishing DB transaction to delete run")
    log.info("Run resources removed")


def delete_project_data(conn, project_id):
    """
    Deletes the mappings and permutations for a given project.

    This is very manual, looking forward to https://github.com/n1analytics/entity-service/issues/133
    """
    log = logger.bind(pid=project_id)
    dp_ids = get_dataprovider_ids(conn, project_id)
    # Note the first context manager begins a database transaction
    with conn:
        with conn.cursor() as cur:
            log.debug("Beginning db transaction to remove result data associated with project")
            cur.execute("""
                DELETE
                FROM run_results
                  USING runs
                WHERE
                    runs.run_id = run_results.run_id AND
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
            log.debug("delete dataproviders with all associated encodings, blocks and upload data.")
            cur.execute("""
                DELETE
                FROM dataproviders
                WHERE
                    id in ({})""".format(','.join(map(str, dp_ids))))
        log.debug("Committing removal of project resource")
