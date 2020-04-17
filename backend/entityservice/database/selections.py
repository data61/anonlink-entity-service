import io
import itertools

from entityservice.database.util import query_db, logger
from entityservice.errors import ProjectDeleted, RunDeleted, DataProviderDeleted


def select_dataprovider_id(db, project_id, receipt_token):
    """
    Given a receipt token get the id of the matching data provider.

    Returns None if token is incorrect.
    """
    sql_query = """
        SELECT dp from dataproviders, uploads
        WHERE
          uploads.dp = dataproviders.id AND
          dataproviders.project = %s AND
          uploads.token = %s
        """
    query_result = query_db(db, sql_query, [project_id, receipt_token], one=True)
    logger.debug("Looking up data provider with auth. {}".format(query_result))
    return query_result['dp'] if query_result is not None else None


def get_dataprovider_ids(db, project_id):
    """Get a list of data provider ids given a project id

    Only returns dataproviders who have uploaded data
    """
    sql_query = """
        SELECT dataproviders.id
        FROM dataproviders
        WHERE
          dataproviders.project = %s AND
          dataproviders.uploaded = 'done'
        ORDER BY dataproviders.id
        """
    query_result = query_db(db, sql_query, [project_id])
    dp_ids = list(map(lambda d: d['id'], query_result))
    return dp_ids


def check_project_exists(db, resource_id):
    sql_query = 'select count(*) from projects WHERE project_id = %s AND marked_for_deletion = false'
    query_result = query_db(db, sql_query, [resource_id], one=True)
    return query_result['count'] == 1


def check_run_exists(db, project_id, run_id):
    sql_query = '''
        SELECT count(*)
        FROM runs
        WHERE 
          project = %s AND
          run_id = %s
        '''
    query_result = query_db(db, sql_query, [project_id, run_id], one=True)
    return query_result['count'] == 1


def get_number_parties_uploaded(db, project_id):
    sql_query = """
        SELECT COUNT(*)
        FROM dataproviders, uploads
        WHERE
          dataproviders.project = %s AND
          uploads.dp = dataproviders.id AND
          dataproviders.uploaded = 'done'
        """
    query_result = query_db(db, sql_query, [project_id], one=True)
    return query_result['count']


def get_encoding_error_count(db, project_id):
    """
    Returns the count of uploads for the given project that are in the state "error".
    """
    sql_query = """
        SELECT count(*)
        FROM dataproviders, uploads
        WHERE
          dataproviders.project = %s AND
          uploads.dp = dataproviders.id AND
          uploads.state = 'error'
        """
    return query_db(db, sql_query, [project_id], one=True)['count']


def get_number_parties_ready(db, resource_id):
    sql_query = """
        SELECT COUNT(*)
        FROM dataproviders, uploads
        WHERE
          dataproviders.project = %s AND
          uploads.dp = dataproviders.id AND
          dataproviders.uploaded = 'done' AND
          uploads.state = 'ready'
        """
    query_result = query_db(db, sql_query, [resource_id], one=True)
    return query_result['count']


def get_run_state(db, run_id):
    logger.info("Selecting run")
    sql_query = """
        SELECT state
        FROM runs
        WHERE
          run_id = %s
        """
    query_result = query_db(db, sql_query, [run_id], one=True)
    state = query_result['state']
    logger.info("Run with run_id={} is in state: {}".format(run_id, state))
    return state


def get_project(db, resource_id):
    sql_query = """
        SELECT * from projects
        WHERE project_id = %s AND marked_for_deletion=FALSE
        """
    return query_db(db, sql_query, [resource_id], one=True)


def get_runs(db, project_id):
    select_query = """
      SELECT run_id, time_added, state 
      FROM runs
      WHERE
        project = %s
    """
    return query_db(db, select_query, [project_id], one=False)


def get_run_state_for_update(db, run_id):
    """
    Get the current run state and acquire a row lock
    (or fail fast if row already locked)
    """
    sql_query = """
        SELECT state from runs
        WHERE 
            run_id = %s
        FOR UPDATE NOWAIT
        """
    return query_db(db, sql_query, [run_id], one=True)['state']


def get_run(db, run_id):
    sql_query = """
        SELECT * from runs
        WHERE run_id = %s
        """
    return query_db(db, sql_query, [run_id], one=True)


def get_project_column(db, project_id, column):
    assert column in {'notes', 'schema', 'parties', 'result_type', 'deleted', 'encoding_size', 'uses_blocking'}
    sql_query = """
        SELECT {} 
        FROM projects
        WHERE project_id = %s
        """.format(column)
    query_result = query_db(db, sql_query, [project_id], one=True)
    if query_result is None:
        raise ProjectDeleted(project_id)
    else:
        return query_result[column]


def get_run_result(db, resource_id):
    """
    Return a Python dictionary mapping the index in A to
    the index in B.

    Note the response is mapping str -> int as both celery and
    postgres prefer keys to be strings.
    """
    sql_query = """
        SELECT result from run_results
        WHERE run = %s
        """
    query_result = query_db(db, sql_query, [resource_id], one=True)
    if query_result is None:
        raise RunDeleted(f"Run {resource_id} not found in database")
    return query_result['result']


def get_project_dataset_sizes(db, project_id):
    """Returns the number of encodings in a dataset."""
    sql_query = """
        SELECT uploads.count
        FROM dataproviders, uploads
        WHERE
          uploads.dp=dataproviders.id AND
          dataproviders.project=%s
        ORDER BY dataproviders.id
        """
    query_result = query_db(db, sql_query, [project_id], one=False)
    dataset_lengths = [r['count'] for r in query_result]
    return dataset_lengths


def get_uploaded_encoding_sizes(db, project_id):
    sql_query = """
        SELECT dp, encoding_size
        FROM dataproviders, uploads
        WHERE
          uploads.dp=dataproviders.id AND
          dataproviders.project=%s
        ORDER BY dataproviders.id
        """
    query_result = query_db(db, sql_query, [project_id], one=False)
    return [(r['dp'], r['encoding_size']) for r in query_result]


def get_smaller_dataset_size_for_project(db, project_id):
    sql_query = """
        SELECT MIN(uploads.count) as smaller
        FROM dataproviders, uploads
        WHERE
          uploads.dp=dataproviders.id AND
          dataproviders.project=%s
        """
    query_result = query_db(db, sql_query, [project_id], one=True)
    return query_result['smaller']


def get_total_comparisons_for_project(db, project_id):
    """
    Returns the number of comparisons that a project requires.

    For each data provider multiple the size of each block, then sum number
    of comparisons in all blocks together.

    :return total number of comparisons for this project
    """
    sql_query = """
        select sum(product) from (select product(count)
        from blocks
        where dp in (
            select id from dataproviders where project = %s
        )
        GROUP BY block_name) as per_block_product
        """
    total_comparisons = query_db(db, sql_query, [project_id], one=True)['sum']
    return total_comparisons


def get_dataprovider_id(db, update_token):
    sql_query = '''
        SELECT id 
        FROM dataproviders 
        WHERE 
          token = %s
        '''
    return query_db(db, sql_query, [update_token], one=True)['id']


def get_uploads_columns(db, dp_id, columns):
    for column in columns:
        assert column in {'ts', 'token', 'file', 'state', 'block_count', 'count', 'encoding_size'}
    sql_query = """
        SELECT {} 
        FROM uploads
        WHERE dp = %s
        """.format(', '.join(columns))
    result = query_db(db, sql_query, [dp_id], one=True)
    if result is None:
        raise DataProviderDeleted(dp_id)
    return [result[column] for column in columns]


def get_encodingblock_ids(db, dp_id, block_id=None, offset=0, limit=None):
    """Yield all encoding ids in either a single block, or all blocks for a given data provider."""
    sql_query = """
        SELECT encoding_id 
        FROM encodingblocks
        WHERE dp = %(dp_id)s
        {}
        ORDER BY
          encoding_ID ASC
        OFFSET %(offset)s
        LIMIT %(limit)s
        """.format("AND block_id = %(block_id)s" if block_id else "")
    # Specifying a name for the cursor creates a server-side cursor, which prevents all of the
    # records from being downloaded at once.
    cur = db.cursor(f'encodingblockfetcher-{dp_id}')
    args = {'dp_id': dp_id, 'block_id': block_id, 'offset': offset, 'limit': limit}
    cur.execute(sql_query, args)
    yield from iterate_cursor_results(cur)


def get_block_metadata(db, dp_id):
    """Yield block id and counts for a given data provider."""
    sql_query = """
        SELECT block_name, count
        FROM blocks
        WHERE dp = %s
        """
    # Specifying a name for the cursor creates a server-side cursor, which prevents all of the
    # records from being downloaded at once.
    cur = db.cursor(f'blockfetcher-{dp_id}')
    args = (dp_id,)
    cur.execute(sql_query, args)
    for block_name, count in iterate_cursor_results(cur, one=False):
        yield block_name.strip(), count


def iterate_cursor_results(cur, one=True, page_size=4096):
    while True:
        rows = cur.fetchmany(page_size)
        if not rows:
            break
        for row in rows:
            if one:
                yield row[0]
            else:
                yield row


def copy_binary_column_from_select_query(cur, select_query, stored_binary_size=132):
    """Yields raw bytes from postgres given a query returning a column containing fixed size bytea data.

    :param select_query: An sql query that select's a single binary column. Include ordering the results.
    :param stored_binary_size: Fixed size of each bytea data.
    :raises AssertionError if the database implements an unhandled extension or the EOF is corrupt.
    """

    copy_to_stream_query = """COPY ({}) TO STDOUT WITH binary""".format(select_query)
    stream = io.BytesIO()
    cur.copy_expert(copy_to_stream_query, stream)

    raw_data = stream.getvalue()

    # Need to read/remove the Postgres Binary Header, Trailer, and the per tuple info
    # https://www.postgresql.org/docs/current/sql-copy.html
    _ignored_header = raw_data[:15]
    header_extension = raw_data[15:19]
    assert header_extension == b'\x00\x00\x00\x00', "Need to implement skipping postgres binary header extension"
    binary_trailer = raw_data[-2:]
    assert binary_trailer == b'\xff\xff', "Corrupt COPY of binary data from postgres"
    raw_data = raw_data[19:-2]

    # The first 6 bytes of each row contains: tuple field count and field length
    per_row_header_size = 6
    size = stored_binary_size + per_row_header_size
    for i in range(0, len(raw_data), size):
        start_index = i + per_row_header_size
        end_index = start_index + stored_binary_size
        yield raw_data[start_index: end_index]


def get_chunk_of_encodings(db, dp_id, encoding_ids, stored_binary_size=132):
    """Yields raw byte encodings for a data provider given the encoding ids.

    :param dp_id: Fetch encodings from this dataprovider (encoding ids are not unique across data providers).
    :param encoding_ids: List of ints of the encoding ids to include.
    :param stored_binary_size: Size of each encoding stored in the database. Including encoding ids.
    """

    cur = db.cursor()

    sql_query = """
    SELECT encoding
    FROM encodings
    WHERE encodings.dp = {}
    AND encodings.encoding_id in ({})
    ORDER BY encoding_id ASC
    """.format(
        dp_id,
        ','.join(map(str, encoding_ids))
    )
    yield from copy_binary_column_from_select_query(cur, sql_query, stored_binary_size=stored_binary_size)


def get_filter_metadata(db, dp_id):
    """
    :return: The filename (which could be None), and the encoding size of the raw clks.
    """
    filename, encoding_size = get_uploads_columns(db, dp_id, ['file', 'encoding_size'])
    if filename is not None:
        filename = filename.strip()
    return filename, encoding_size


def get_encoding_metadata(db, dp_id):
    """
    :return: The number of encodings and number of blocks of the uploaded data.
    """
    return get_uploads_columns(db, dp_id, ['count', 'block_count'])


def get_project_schema_encoding_size(db, project_id):
    """
    Return the project's `encoding_size`, first looking in the
    project table's `encoding_size` column, with a fallback to
    calculating it from the number of bits set in the linkage schema.

    :return: The expected size of uploaded encodings in bytes or None.
    """
    sql_query = """
        SELECT
            coalesce(
                encoding_size,
                case 
                    when (schema->'clkConfig') IS NULL THEN null                
                    when (schema->'clkConfig'->>'l') IS NULL THEN null
                    else (schema->'clkConfig'->>'l')::integer/8
                end
            ) AS encoding_size
        FROM projects
        WHERE project_id = %s
        """.format(project_id)
    return query_db(db, sql_query, [project_id], one=True)['encoding_size']


def get_project_encoding_size(db, project_id):
    return get_project_column(db, project_id, 'encoding_size')


def get_permutation_result(db, dp_id, run_id):
    # Note doesn't include the mask, just the permutation for given dp
    sql_query = """
        SELECT permutation FROM permutations
        WHERE
          dp = %s AND
          run = %s

        """
    return query_db(db, sql_query, [dp_id, run_id], one=True)['permutation']


def get_permutation_unencrypted_mask(db, project_id, run_id):
    sql_query = """
        SELECT raw 
        FROM permutation_masks
        WHERE 
          project = %s AND
          run = %s
        """
    return query_db(db, sql_query, [project_id, run_id], one=True)['raw']


def get_similarity_scores_filename(db, run_id):
    sql_query = """
        SELECT file FROM similarity_scores
        WHERE
          run = %s
        """
    return query_db(db, sql_query, [run_id], one=True)['file'].strip()


def get_run_status(db, run_id):
    sql_query = """
            SELECT state, stage, type, time_added, time_started, time_completed
            FROM runs
            WHERE
              run_id = %s
            """
    return query_db(db, sql_query, [run_id], one=True)


def get_all_objects_for_project(db, project_id):
    result_type = get_project_column(db, project_id, 'result_type')
    object_store_files = []
    dps = query_db(db, """
        SELECT id
        FROM dataproviders
        WHERE project = %s
        """, [project_id])

    for dp in dps:
        clk_file_ref = query_db(db, """
            SELECT file FROM uploads
            WHERE dp = %s
            """, [dp['id']], one=True)

        if clk_file_ref is not None:
            logger.info("blooming data file found: {}".format(clk_file_ref))
            object_store_files.append(clk_file_ref['file'])

    if result_type == "similarity_scores":
        similarity_files = get_project_similarity_files(db, project_id)
        object_store_files.extend(similarity_files)

    return object_store_files


def get_project_similarity_files(db, project_id):
    query_response = query_db(db, """
            SELECT 
              similarity_scores.file
            FROM 
              similarity_scores, runs
            WHERE 
              runs.run_id = similarity_scores.run AND
              runs.project = %s
            """, [project_id])
    similarity_files = [res['file'] for res in query_response]
    return similarity_files


def get_similarity_file_for_run(db, run_id):
    query_response = query_db(db, """
            SELECT 
              similarity_scores.file
            FROM 
              similarity_scores
            WHERE 
              similarity_scores.run = %s
            """, [run_id])
    similarity_files = [res['file'] for res in query_response]
    if len(similarity_files):
        assert len(similarity_files) == 1, "More than one similarity score file associated with a single run"
        return similarity_files[0]
