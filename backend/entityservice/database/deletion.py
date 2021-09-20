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

    # We need to detach the partitions first, as detaching and then dropping does not need an ACCESS EXCLUSIVE LOCK on
    # the partition parent table.

    def _execute_transaction_with_advisory_lock(sql_stmts, lock_id):
        # Note the first context manager begins a database transaction
        with conn:
            with conn.cursor() as cur:
                log.info(f"try to acquire advisory lock {lock_id}")
                cur.execute("SELECT pg_advisory_xact_lock(42)")
                log.info(f"got it lock {lock_id}")
                for stmt in sql_stmts:
                    cur.execute(stmt)

    # detaching partitions of encodingblocks and encodings first such that we can drop tables without having to worry
    # about locks
    _execute_transaction_with_advisory_lock(
        [f"ALTER TABLE encodings DETACH PARTITION encodings_{dp_id}" for dp_id in dp_ids], 42)
    # detaching the encodingblocks partition can create a deadlock. As encodingsblocks has a foreign key to the blocks
    # table, it will first lock encodingblocks and then try to lock the blocks table. This competes with
    # - inserting into encodingblocks will first lock blocks and then tries to lock encodingblocks...
    # - delete from dataproviders also first locks the blocks table and then tries to lock the encodingblocks table.
    # Therefore, we explicitly request the lock on the blocks tables first before altering encodingblocks.
    _execute_transaction_with_advisory_lock(
        [f"ALTER TABLE encodingblocks DETACH PARTITION encodingblocks_{dp_id}" for dp_id in dp_ids], 42)

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

            log.debug("delete dataproviders with all associated blocks and upload data.")
            cur.execute("""
                DELETE
                FROM dataproviders
                WHERE
                    id in ({})""".format(','.join(map(str, dp_ids))))
            for dp_id in dp_ids:
                cur.execute(f"DROP TABLE encodings_{dp_id}")
                cur.execute(f"DROP TABLE encodingblocks_{dp_id}")
        log.debug("Committing removal of project resource")
