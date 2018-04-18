# Insertion Queries

import psycopg2
from entityservice.database.util import execute_returning_id, logger


def insert_new_project(cur, result_type, schema, access_token, project_id, num_parties, notes):
    return execute_returning_id(cur,
                                """
                                INSERT INTO projects
                                (project_id, access_token, schema, notes, parties, result_type)
                                VALUES
                                (%s, %s, %s, %s, %s, %s)
                                RETURNING project_id;
                                """,
                                [
                                    project_id,
                                    access_token,
                                    psycopg2.extras.Json(schema),
                                    notes,
                                    num_parties,
                                    result_type
                                ])


def insert_new_run(cur, run_id, project_id, threshold, notes=''):
    return execute_returning_id(cur,
                                """
                                INSERT INTO runs
                                (run_id, project, notes, threshold, state)
                                VALUES
                                (%s, %s, false, %s, %s, %s)
                                RETURNING project_id;
                                """,
                                [
                                    run_id,
                                    project_id,
                                    notes,
                                    threshold,
                                    'queued'
                                ])


def insert_paillier(cur, public_key, context):
    return execute_returning_id(cur, """
            INSERT INTO paillier
            (public_key, context)
            VALUES
            (%s, %s)
            RETURNING id;
            """,
                                [
                psycopg2.extras.Json(public_key),
                psycopg2.extras.Json(context)
            ]
                                )


def insert_empty_encrypted_mask(cur, project_id, run_id, pid):
    return execute_returning_id(cur,
                                """
                                INSERT INTO encrypted_permutation_masks
                                (project, run, paillier)
                                VALUES
                                (%s, %s, %s)
                                RETURNING id;
                                """,
                                [
                                    project_id,
                                    run_id,
                                    pid
                                ]
                                )


def insert_dataprovider(cur, auth_token, project_id):
    return execute_returning_id(cur,
                                """
                                INSERT INTO dataproviders
                                (project, token)
                                VALUES
                                (%s, %s)
                                RETURNING id
                                """,
                                [project_id, auth_token])


def insert_filter_data(db, clks_filename, dp_id, receipt_token, size):

    with db.cursor() as cur:
        logger.info("Adding blooming data to database")
        cur.execute("""
            INSERT INTO bloomingdata
            (dp, token, file, size, state)
            VALUES
            (%s, %s, %s, %s, %s)
            """,
            [
                dp_id,
                receipt_token,
                clks_filename,
                size,
                'pending'
             ])

        cur.execute("""
            UPDATE dataproviders
            SET uploaded = TRUE
            WHERE id = %s
            """, [dp_id])

    db.commit()


def update_filter_data(db, clks_filename, dp_id, state='ready'):
    with db.cursor() as cur:
        logger.info("Updating database with info about hashes")
        cur.execute("""
            UPDATE bloomingdata
            SET
              state = %s,
              file = %s
            WHERE
              dp = %s
            """,
            [
                state,
                clks_filename,
                dp_id,
             ])
    db.commit()


def update_run_chunk(db, resource_id, chunk_size):
    with db.cursor() as cur:
        cur.execute("""
            UPDATE runs
            SET
              chunk_size = %s
            WHERE
              run_id = %s
            """,
            [
                chunk_size,
                resource_id
             ])
    db.commit()