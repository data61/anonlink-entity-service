# Insertion Queries

import psycopg2
from entityservice.database.util import execute_returning_id, logger


def insert_new_project(cur, result_type, schema, access_token, project_id, num_parties, name, notes):
    sql_query = """
        INSERT INTO projects
        (project_id, name, access_token, schema, notes, parties, result_type)
        VALUES
        (%s, %s, %s, %s, %s, %s, %s)
        RETURNING project_id;
        """
    return execute_returning_id(cur, sql_query,
                                [project_id, name, access_token, psycopg2.extras.Json(schema), notes, num_parties,
                                 result_type])


def insert_new_run(db, run_id, project_id, threshold, notes=''):
    sql_query = """
        INSERT INTO runs
        (run_id, project, notes, threshold, state)
        VALUES
        (%s, %s, %s, %s, %s)
        RETURNING run_id;
        """
    with db.cursor() as cur:
        run_id = execute_returning_id(cur, sql_query, [run_id, project_id, notes, threshold, 'queued'])
    db.commit()
    return run_id


def insert_paillier(cur, public_key, context):
    sql_query = """
        INSERT INTO paillier
        (public_key, context)
        VALUES
        (%s, %s)
        RETURNING id;
        """
    return execute_returning_id(cur, sql_query, [psycopg2.extras.Json(public_key), psycopg2.extras.Json(context)])


def insert_empty_encrypted_mask(cur, project_id, run_id, pid):
    sql_query = """
        INSERT INTO encrypted_permutation_masks
        (project, run, paillier)
        VALUES
        (%s, %s, %s)
        RETURNING id;
        """
    return execute_returning_id(cur, sql_query, [project_id, run_id, pid])


def insert_dataprovider(cur, auth_token, project_id):
    sql_query = """
        INSERT INTO dataproviders
        (project, token)
        VALUES
        (%s, %s)
        RETURNING id
        """
    return execute_returning_id(cur, sql_query, [project_id, auth_token])


def insert_filter_data(db, clks_filename, dp_id, receipt_token, size):
    logger.info("Adding CLK data to database")
    sql_insertion_query = """
        INSERT INTO bloomingdata
        (dp, token, file, size, state)
        VALUES
        (%s, %s, %s, %s, %s)
        """

    sql_update = """
        UPDATE dataproviders
        SET uploaded = TRUE
        WHERE id = %s
        """

    with db.cursor() as cur:
        cur.execute(sql_insertion_query, [dp_id, receipt_token, clks_filename, size, 'pending'])
        cur.execute(sql_update, [dp_id])

    db.commit()


def update_filter_data(db, clks_filename, dp_id, state='ready'):
    sql_query = """
        UPDATE bloomingdata
        SET
          state = %s,
          file = %s
        WHERE
          dp = %s
        """

    logger.info("Updating database with info about hashes")
    with db.cursor() as cur:
        cur.execute(sql_query, [state, clks_filename, dp_id,])
    db.commit()


def update_run_chunk(db, resource_id, chunk_size):
    sql_query = """
        UPDATE runs
        SET
          chunk_size = %s
        WHERE
          run_id = %s
        """
    with db.cursor() as cur:
        cur.execute(sql_query, [chunk_size, resource_id])
    db.commit()
