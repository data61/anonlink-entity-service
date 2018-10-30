from entityservice.database.util import query_db, logger
from entityservice.errors import ProjectDeleted, RunDeleted, DataProviderDeleted


def select_dataprovider_id(db, project_id, receipt_token):
    """
    Given a receipt token get the id of the matching data provider.

    Returns None if token is incorrect.
    """
    sql_query = """
        SELECT dp from dataproviders, bloomingdata
        WHERE
          bloomingdata.dp = dataproviders.id AND
          dataproviders.project = %s AND
          bloomingdata.token = %s
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
          dataproviders.uploaded = TRUE
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
        FROM dataproviders, bloomingdata
        WHERE
          dataproviders.project = %s AND
          bloomingdata.dp = dataproviders.id AND
          dataproviders.uploaded = TRUE
        """
    query_result = query_db(db, sql_query, [project_id], one=True)
    return query_result['count']


def get_encoding_error_count(db, project_id):
    sql_query = """
        SELECT count(*)
        FROM dataproviders, bloomingdata
        WHERE
          dataproviders.project = %s AND
          bloomingdata.dp = dataproviders.id AND
          bloomingdata.state != 'error'
        """
    return query_db(db, sql_query, [project_id], one=True)['count']


def get_number_parties_ready(db, resource_id):
    sql_query = """
        SELECT COUNT(*)
        FROM dataproviders, bloomingdata
        WHERE
          dataproviders.project = %s AND
          bloomingdata.dp = dataproviders.id AND
          dataproviders.uploaded = TRUE AND
          bloomingdata.state = 'ready'
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


def get_run(db, run_id):
    sql_query = """
        SELECT * from runs
        WHERE run_id = %s
        """
    return query_db(db, sql_query, [run_id], one=True)


def get_project_column(db, project_id, column):
    assert column in {'notes', 'schema', 'parties', 'result_type', 'deleted', 'encoding_size'}
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
    sql_query = """
        SELECT bloomingdata.count
        FROM dataproviders, bloomingdata
        WHERE
          bloomingdata.dp=dataproviders.id AND
          dataproviders.project=%s
        ORDER BY dataproviders.id
        """
    query_result = query_db(db, sql_query, [project_id], one=False)
    dataset_lengths = [r['count'] for r in query_result]
    return dataset_lengths


def get_uploaded_encoding_sizes(db, project_id):
    sql_query = """
        SELECT bloomingdata.encoding_size
        FROM dataproviders, bloomingdata
        WHERE
          bloomingdata.dp=dataproviders.id AND
          dataproviders.project=%s
        ORDER BY dataproviders.id
        """
    query_result = query_db(db, sql_query, [project_id], one=False)
    encoding_sizes = [r['encoding_size'] for r in query_result]
    return encoding_sizes


def get_smaller_dataset_size_for_project(db, project_id):
    sql_query = """
        SELECT MIN(bloomingdata.count) as smaller
        FROM dataproviders, bloomingdata
        WHERE
          bloomingdata.dp=dataproviders.id AND
          dataproviders.project=%s
        """
    query_result = query_db(db, sql_query, [project_id], one=True)
    return query_result['smaller']


def get_total_comparisons_for_project(db, project_id):
    """
    :return total number of comparisons for this project
    """
    sql_query = """
        SELECT bloomingdata.count as rows
        from dataproviders, bloomingdata
        where
          bloomingdata.dp=dataproviders.id AND
          dataproviders.project=%s
        """
    query_result = query_db(db, sql_query, [project_id])

    if len(query_result) == 2:
        total_comparisons = query_result[0]['rows'] * query_result[1]['rows']
    else:
        total_comparisons = 'NA'

    return total_comparisons


def get_dataprovider_id(db, update_token):
    sql_query = '''
        SELECT id 
        FROM dataproviders 
        WHERE 
          token = %s
        '''
    return query_db(db, sql_query, [update_token], one=True)['id']


def get_bloomingdata_column(db, dp_id, column):
    assert column in {'ts', 'token', 'file', 'state', 'count'}
    sql_query = """
        SELECT {} 
        FROM bloomingdata
        WHERE dp = %s
        """.format(column)
    result = query_db(db, sql_query, [dp_id], one=True)
    if result is None:
        raise DataProviderDeleted(dp_id)
    else:
        return result[column]


def get_filter_metadata(db, dp_id):
    """
    :return: The filename of the raw clks.
    """
    return get_bloomingdata_column(db, dp_id, 'file').strip()


def get_number_of_hashes(db, dp_id):
    """
    :return: The count of the uploaded encodings.
    """
    return get_bloomingdata_column(db, dp_id, 'count')


def get_project_schema_encoding_size(db, project_id):
    """
    :return: The expected size of uploaded encodings.
    """
    sql_query = """
        SELECT
            schema->'clkConfig'->'l' as num_bits
        FROM projects
        WHERE project_id = %s
        """.format(project_id)
    res = query_db(db, sql_query, [project_id], one=True)
    if res is not None and res['num_bits'] is not None:
        return res['num_bits']//8
    else:
        return None


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
    return query_db(db, sql_query, [run_id], one=True)['file']


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
            SELECT file FROM bloomingdata
            WHERE dp = %s
            """, [dp['id']], one=True)

        if clk_file_ref is not None:
            logger.info("blooming data file found: {}".format(clk_file_ref))
            object_store_files.append(clk_file_ref['file'])

    if result_type == "similarity_scores":
        query_response = query_db(db, """
            SELECT 
              similarity_scores.file
            FROM 
              similarity_scores, runs
            WHERE 
              runs.run_id = similarity_scores.run AND
              runs.project = %s
            """, [project_id])
        similarity_files = [res[0]['file'] for res in query_response]
        object_store_files.extend(similarity_files)

    return object_store_files
