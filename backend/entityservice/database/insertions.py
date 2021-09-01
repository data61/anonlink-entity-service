from typing import List

import opentracing
import psycopg2
import psycopg2.extras

from entityservice.database.util import execute_returning_id, logger, query_db, compute_encoding_ids
from entityservice.errors import RunDeleted
from entityservice.database.selections import get_block_metadata


def insert_new_project(cur, result_type, schema, access_token, project_id, num_parties, name, notes, uses_blocking):
    sql_query = """
        INSERT INTO projects
        (project_id, name, access_token, schema, notes, parties, result_type, uses_blocking)
        VALUES
        (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING project_id;
        """
    return execute_returning_id(cur, sql_query,
                                [project_id, name, access_token, psycopg2.extras.Json(schema), notes, num_parties,
                                 result_type, uses_blocking])


def insert_new_run(db, run_id, project_id, threshold, name, type, notes=''):
    sql_query = """
        INSERT INTO runs
        (run_id, project, name, notes, threshold, state, type)
        VALUES
        (%s, %s, %s, %s, %s, %s, %s)
        RETURNING run_id;
        """
    with db.cursor() as cur:
        run_id = execute_returning_id(cur, sql_query,
                                      [run_id, project_id, name, notes, threshold, 'created', type])
    return run_id


def insert_dataprovider(cur, auth_token, project_id):
    sql_query = """
        INSERT INTO dataproviders
        (project, token, uploaded)
        VALUES
        (%s, %s, 'not_started')
        RETURNING id
        """
    return execute_returning_id(cur, sql_query, [project_id, auth_token])


def insert_blocking_metadata(db, dp_id, blocks):
    """
    Insert new entries into the blocks table.

    :param blocks: A dict mapping block id to the number of encodings per block.
    """
    logger.info("Adding blocking metadata to database")
    sql_insertion_query = """
        INSERT INTO blocks
        (dp, block_name, count, state)
        VALUES %s
        """

    logger.info("Preparing SQL for bulk insert of blocks")
    values = [(dp_id, block_name, blocks[block_name], 'pending') for block_name in blocks]

    with db.cursor() as cur:
        psycopg2.extras.execute_values(cur, sql_insertion_query, values)


def insert_encoding_metadata(db, clks_filename, dp_id, receipt_token, encoding_count, block_count):
    logger.info("Adding metadata on encoded entities to database")
    sql_insertion_query = """
        INSERT INTO uploads
        (dp, token, file, count, block_count, state)
        VALUES
        (%s, %s, %s, %s, %s, %s)
        """

    with db.cursor() as cur:
        cur.execute(sql_insertion_query, [dp_id, receipt_token, clks_filename, encoding_count, block_count, 'pending'])


def insert_encodings_into_blocks(db, dp_id: int, block_names: List[List[str]], entity_ids: List[int],
                                 encodings: List[bytes], page_size: int = 4096):
    """
    Bulk load blocking and encoding data into the database.
    See https://hakibenita.com/fast-load-data-python-postgresql#copy-data-from-a-string-iterator-with-buffer-size

    :param page_size:
        Maximum number of rows to fetch in a given sql statement/network transfer. A larger page size
        will require more local memory, but could be faster due to less network transfers.

    """
    ## first we have to look up the block numbers corresponding to the given block_names
    block_info_iter = get_block_metadata(db, dp_id)
    block_lookup = {bl_name: bl_id for bl_name, bl_id, _ in block_info_iter}

    encodings_insertion_query = "INSERT INTO encodings (encoding_id, encoding, dp) VALUES %s"
    blocks_insertion_query = "INSERT INTO encodingblocks (dp, entity_id, encoding_id, block_id) VALUES %s"
    # we differentiate between entity_id and encoding_id.
    # The entity_id is the id that the dataprovider assigns to an entity. Usually the row number of that entity in the
    # dataset.
    # The encoding_id is used internally to address encodings uniquely.

    encoding_ids = compute_encoding_ids(map(int, entity_ids), dp_id)
    encoding_data = ((eid, encoding, dp_id) for eid, encoding in zip(encoding_ids, encodings))

    def block_data_generator(entity_ids, encoding_ids, block_ids):
        for en_id, eid, block_ids in zip(entity_ids, encoding_ids, block_ids):
            for block_id in block_ids:
                yield dp_id, en_id, eid, block_lookup[block_id]

    with db.cursor() as cur:
        with opentracing.tracer.start_span('insert-encodings-to-db'):
            psycopg2.extras.execute_values(cur, encodings_insertion_query, encoding_data, page_size=page_size)
        with opentracing.tracer.start_span('insert-encodingblocks-to-db'):
            psycopg2.extras.execute_values(cur,
                                           blocks_insertion_query,
                                           list(block_data_generator(entity_ids, encoding_ids, block_names)),
                                           page_size=page_size)


def set_dataprovider_upload_state(db, dp_id, state='error'):
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
                  (run_id, result)
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
        UPDATE uploads
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


def update_blocks_state(db, dp_id, blocks, state):
    assert state in {'pending', 'ready', 'error'}
    sql_query = """
        UPDATE blocks
        SET
          state = %s
        WHERE
          dp = %s AND
          block_name in %s
        """

    with db.cursor() as cur:
        cur.execute(sql_query, [
            state,
            dp_id,
            tuple(blocks)
        ])

def update_encoding_metadata_set_encoding_size(db, dp_id, encoding_size):
    sql_query = """
        UPDATE uploads
        SET
          encoding_size = %s
        WHERE
          dp = %s
        """

    logger.info(f"Updating uploads table for dp {dp_id} with encoding size ({encoding_size})")
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


def update_run_mark_failure(conn, run_id, err_msg):
    with conn.cursor() as cur:
        sql_query = """
            UPDATE runs SET
              state = 'error',
              time_completed = now(),
              error_msg = %s
            WHERE
              run_id = %s
            """
        cur.execute(sql_query, [err_msg, run_id])


def update_project_mark_all_runs_failed(conn, project_id, err_msg):
    with conn.cursor() as cur:
        sql_query = """
            UPDATE runs SET
              state = 'error',
              time_completed = now(),
              error_msg = %s
            WHERE
              project = %s
            """
        cur.execute(sql_query, [err_msg, project_id])


def update_dataprovider_uploaded_state(conn, project_id, dp_id, state):
    with conn.cursor() as cur:
        sql_query = """
            UPDATE dataproviders SET
              uploaded = %s
            WHERE
              id = %s AND
              project = %s
            """
        cur.execute(sql_query, [state, dp_id, project_id])


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
              state = 'created' AND project = %s
            RETURNING
              run_id;
        """
        cur.execute(sql_query, [project_id])
        res = cur.fetchall()
    if res is None:
        res = []
    return res


def is_dataprovider_allowed_to_upload_and_lock(db, dp_id):
    """
    This method returns true if the data provider is allowed to upload their encodings.

    A dataprovider is not allowed to upload clks if they has already uploaded them, or if the upload is in progress.
    This method will lock the resource by setting the upload state to `in_progress` and returning `true`.
    Note that the upload state can be `error`, in which case we allow the dataprovider to re-try uploading
    her clks not to block a project if a failure occurred.
    """
    logger.debug("Setting dataprovider {} upload state to `in_progress``".format(dp_id))
    sql_update = """
        UPDATE dataproviders
        SET uploaded = 'in_progress'
        WHERE id = %s and uploaded != 'done' and uploaded != 'in_progress'
        RETURNING id, uploaded
        """
    query_response = query_db(db, sql_update, [dp_id])
    length = len(query_response)
    if length < 1:
        return False
    elif length > 1:
        logger.error("{} rows in the table `dataproviders` are associated to the same dataprovider id {}, while each"
                     " dataprovider id should be unique.".format(length, dp_id))
        raise ValueError("Houston, we have a problem!!! This dataprovider has uploaded multiple times")
    return True
