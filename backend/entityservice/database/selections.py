import io
import itertools

from entityservice.database.util import query_db, logger, binary_format, compute_encoding_ids
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
        WHERE run_id = %s
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

    For each block:
        for each pairwise combination of data providers in each block:
            multiply the block sizes together
        then sum number of comparisons for each block
    Sum the number of comparisons in all blocks together.

    :return total number of comparisons for this project
    """

    # The full computation is *hard* to do in postgres, so we return an array of sizes
    # for each block and then use Python to find the pairwise combinations.
    sql_query = """
        select block_name, array_agg(count) as counts
        from blocks
        where dp in (
            select id from dataproviders where project = %s
        )
        group by block_name
        """

    query_results = query_db(db, sql_query, [project_id])
    total_comparisons = 0
    for block in query_results:
        num_comparisons_in_block = sum(c0 * c1 for c0, c1 in itertools.combinations(block['counts'], 2))
        total_comparisons += num_comparisons_in_block

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
    """Yield all entity ids in either a single block, or all blocks for a given data provider."""
    sql_query = """
        SELECT entity_id 
        FROM encodingblocks
        WHERE dp = %(dp_id)s
        {}
        ORDER BY
          entity_ID ASC
        OFFSET %(offset)s
        LIMIT %(limit)s
        """.format("AND block_id = %(block_id)s" if block_id else "")
    # Specifying a name for the cursor creates a server-side cursor, which prevents all of the
    # records from being downloaded at once.
    cur_name = f'encodingblockfetcher-{dp_id}'
    if block_id:
        cur_name = f'encodingblockfetcher-{dp_id}-{block_id}'
    cur = db.cursor(cur_name)
    args = {'dp_id': dp_id, 'block_id': block_id, 'offset': offset, 'limit': limit}
    cur.execute(sql_query, args)
    yield from iterate_cursor_results(cur)


def get_block_metadata(db, dp_id):
    """Yield block name, block id and counts for a given data provider."""
    sql_query = """
        SELECT block_name, block_id, count
        FROM blocks
        WHERE dp = %s
        """
    # Specifying a name for the cursor creates a server-side cursor, which prevents all of the
    # records from being downloaded at once.
    cur = db.cursor(f'blockfetcher-{dp_id}')
    args = (dp_id,)
    cur.execute(sql_query, args)
    for block_name, block_id, count in iterate_cursor_results(cur, one=False):
        yield block_name.strip(), block_id, count
    cur.close()


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


def execute_select_query_in_binary(cur, select_query):
    """Yields raw bytes from postgres given a query.

    :param cur: db cursor
    :param select_query: An sql query
    :raises AssertionError if the database implements an unhandled extension or the EOF is corrupt.
    """

    copy_to_stream_query = """COPY ({}) TO STDOUT WITH binary""".format(select_query)
    stream = io.BytesIO()
    cur.copy_expert(copy_to_stream_query, stream)

    for row in binary_format(stream):
        yield row


def get_chunk_of_encodings(db, dp_id, entity_ids, stored_binary_size=132):
    """Yields raw byte encodings for a data provider given the encoding ids.

    :param dp_id: Fetch encodings from this dataprovider (encoding ids are not unique across data providers).
    :param entity_ids: List of ints of the entity ids to include.
    :param stored_binary_size: Size of each encoding stored in the database. Including encoding ids.
    """

    cur = db.cursor()

    sql_query = """
    SELECT encoding
    FROM encodings
    WHERE encodings.encoding_id in ({})
    ORDER BY encoding_id ASC
    """.format(
        ','.join(map(str, compute_encoding_ids(entity_ids, dp_id)))
    )
    yield from execute_select_query_in_binary(cur, sql_query)


def get_encodings_of_multiple_blocks(db, dp_id, block_ids):

    cur = db.cursor()
    sql_query = """
    SELECT encodingblocks.block_id, encodingblocks.entity_id, encodings.encoding 
    FROM encodingblocks, encodings
    WHERE
      encodingblocks.dp = {} AND
      encodingblocks.encoding_id = encodings.encoding_id AND 
      encodingblocks.block_id IN ({})
    ORDER BY
        block_id asc, entity_id asc
    """.format(dp_id, ",".join(map(lambda s: f"'{s}'", block_ids)))

    for row in execute_select_query_in_binary(cur, sql_query):
        if len(row) != 3:
            logger.warning(f'something went wrong! Got a row with this: {row}')
        bin_block_id, bin_encoding_id, bin_encoding = row
        yield int.from_bytes(bin_block_id, byteorder='big'), int.from_bytes(bin_encoding_id, byteorder='big'), bin_encoding


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
            SELECT state, stage, type, time_added, time_started, time_completed, error_msg
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

        if clk_file_ref is not None and clk_file_ref['file'] is not None:
            logger.info("upload record found: {}".format(clk_file_ref))
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
