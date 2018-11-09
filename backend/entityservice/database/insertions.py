# Insertion Queries

import psycopg2
import psycopg2.extras
from entityservice.database.util import execute_returning_id, logger
from entityservice.errors import RunDeleted


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


def insert_new_run(db, run_id, project_id, threshold, name, type, notes=''):
    sql_query = """
        INSERT INTO runs
        (run_id, project, name, notes, threshold, state, type)
        VALUES
        (%s, %s, %s, %s, %s, %s, %s)
        RETURNING run_id;
        """
    with db.cursor() as cur:
        run_id = execute_returning_id(cur, sql_query, [run_id, project_id, name, notes, threshold, 'created', type])
    return run_id


def insert_dataprovider(cur, auth_token, project_id):
    sql_query = """
        INSERT INTO dataproviders
        (project, token)
        VALUES
        (%s, %s)
        RETURNING id
        """
    return execute_returning_id(cur, sql_query, [project_id, auth_token])


def insert_encoding_metadata(db, clks_filename, dp_id, receipt_token, count):
    logger.info("Adding metadata on encoded entities to database")
    sql_insertion_query = """
        INSERT INTO bloomingdata
        (dp, token, file, count, state)
        VALUES
        (%s, %s, %s, %s, %s)
        """

    with db.cursor() as cur:
        cur.execute(sql_insertion_query, [dp_id, receipt_token, clks_filename, count, 'pending'])

    set_dataprovider_upload_state(db, dp_id, True)


def set_dataprovider_upload_state(db, dp_id, state=True):
    logger.debug("Setting dataprovider {} upload state to {}".format(dp_id, state))
    sql_update = """
        UPDATE dataproviders
        SET uploaded = %s
        WHERE id = %s
        """

    with db.cursor() as cur:
        cur.execute(sql_update, [state, dp_id])


def insert_similarity_score_file(db, run_id, filename):
    with db.cursor() as cur:
        insertion_query = """
            INSERT into similarity_scores
              (run, file)
            VALUES
              (%s, %s)
            RETURNING id;
            """
        try:
            result_id = execute_returning_id(cur, insertion_query, [run_id, filename])
        except psycopg2.IntegrityError as e:
            raise RunDeleted(run_id)
    return result_id


def insert_mapping_result(db, run_id, mapping):
    try:
        with db.cursor() as cur:
            insertion_query = """
                INSERT into run_results
                  (run, result)
                VALUES
                  (%s, %s)
                RETURNING id;
                """
            result_id = execute_returning_id(cur, insertion_query, [run_id, psycopg2.extras.Json(mapping)])
    except psycopg2.IntegrityError as e:
        raise RunDeleted(run_id)
    return result_id


def insert_permutation(conn, dp_id, run_id, perm_list):
    sql_insertion_query = """
        INSERT INTO permutations
          (dp, run, permutation)
        VALUES
          (%s, %s, %s)
        """
    try:
        with conn.cursor() as cur:
            cur.execute(sql_insertion_query, [dp_id, run_id, psycopg2.extras.Json(perm_list)])
    except psycopg2.IntegrityError:
        raise RunDeleted(run_id)


def insert_permutation_mask(conn, project_id, run_id, mask_list):
    sql_insertion_query = """
        INSERT INTO permutation_masks
          (project, run, raw)
        VALUES
          (%s, %s, %s)
        """
    json_mask = psycopg2.extras.Json(mask_list)
    try:
        with conn.cursor() as cur:
            cur.execute(sql_insertion_query, [project_id, run_id, json_mask])
    except psycopg2.IntegrityError:
        raise RunDeleted(run_id)


def update_encoding_metadata(db, clks_filename, dp_id, state):
    sql_query = """
        UPDATE bloomingdata
        SET
          state = %s,
          file = %s
        WHERE
          dp = %s
        """

    logger.info("Updating database with info about encodings")
    with db.cursor() as cur:
        cur.execute(sql_query, [
            state,
            clks_filename,
            dp_id,
        ])


def update_encoding_metadata_set_encoding_size(db, dp_id, encoding_size):
    sql_query = """
        UPDATE bloomingdata
        SET
          encoding_size = %s
        WHERE
          dp = %s
        """

    logger.info("Updating database with info about encodings")
    with db.cursor() as cur:
        cur.execute(sql_query, [
            encoding_size,
            dp_id,
        ])


def set_project_encoding_size(db, project_id, encoding_size):
    sql_query = """
        UPDATE projects
        SET
          encoding_size = %s
        WHERE
          project_id = %s
        """
    logger.debug("Updating database with project encoding size")
    with db.cursor() as cur:
        cur.execute(sql_query, [encoding_size, project_id])


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


def update_run_set_started(db, run_id):
    with db.cursor() as cur:
        sql_query = """
            UPDATE runs SET
              state = 'running',
              time_started = now()
            WHERE
              run_id = %s
            """
        cur.execute(sql_query, [run_id])


def update_run_mark_complete(db, run_id):
    with db.cursor() as cur:
        sql_query = """
            UPDATE runs SET
              state = 'completed',
              time_completed = now()
            WHERE
              run_id = %s
            """
        cur.execute(sql_query, [run_id])


def update_run_mark_failure(conn, run_id):
    with conn.cursor() as cur:
        sql_query = """
            UPDATE runs SET
              state = 'error',
              time_completed = now()
            WHERE
              run_id = %s
            """
        cur.execute(sql_query, [run_id])


def update_run_mark_queued(db, run_id):
    with db.cursor() as cur:
        sql_query = """
            UPDATE runs SET
              state = 'queued'
            WHERE
              run_id = %s
            """
        cur.execute(sql_query, [run_id])


def mark_project_deleted(db, project_id):
    with db.cursor() as cur:
        sql_query = """
            UPDATE projects SET
              marked_for_deletion = TRUE 
            WHERE
              project_id = %s
            """
        cur.execute(sql_query, [project_id])


def progress_run_stage(db, run_id):
    try:
        with db.cursor() as cur:
            sql_query = """
                UPDATE runs SET
                  stage = stage + 1
                WHERE
                  run_id = %s
                """
            cur.execute(sql_query, [run_id])
    except psycopg2.Error as e:
        logger.warning(e)
        raise RunDeleted(run_id)


def get_created_runs_and_queue(db, project_id):
    """
    returns the run_ids of all runs for this project who's state is 'created' and sets the state of those runs
    to 'queued'.
    This is necessary to avoid a race condition which led to executing a run twice. (#194)
    """
    with db.cursor() as cur:
        sql_query = """
            UPDATE runs SET
              state = 'queued'
            WHERE
              state IN ('created', 'queued') AND project = %s
            RETURNING
              run_id;
        """
        cur.execute(sql_query, [project_id])
        res = cur.fetchall()
    if res is None:
        res = []
    return res
