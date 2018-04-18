from entityservice.database.util import query_db, logger


def select_dataprovider_id(db, project_id, receipt_token):
    """
    Given a receipt token get the id of the matching data provider.

    Returns None if token is incorrect.
    """
    res = query_db(db, """
        select dp from dataproviders, bloomingdata
        WHERE
          bloomingdata.dp = dataproviders.id AND
          dataproviders.project = %s AND
          bloomingdata.token = %s
        """, [project_id, receipt_token], one=True)

    logger.debug("Looking up data provider with auth. {}".format(res))
    return res['dp'] if res is not None else None


def get_dataprovider_ids(db, project_id):
    """Get a list of data provider ids given a project id

    Only returns dataproviders who have uploaded data
    """
    dp_ids = list(map(lambda d: d['id'], query_db(db, """
            SELECT dataproviders.id
            FROM dataproviders
            WHERE
              dataproviders.project = %s AND
              dataproviders.uploaded = TRUE
            """, [project_id])))
    return dp_ids


def check_project_exists(db, resource_id):
    return query_db(db,
        'select count(*) from projects WHERE project_id = %s',
                    [resource_id], one=True)['count'] == 1


def get_number_parties_uploaded(db, resource_id):
    return query_db(db, """
        SELECT COUNT(*)
        FROM dataproviders, bloomingdata
        WHERE
          dataproviders.project = %s AND
          bloomingdata.dp = dataproviders.id AND
          dataproviders.uploaded = TRUE AND
          bloomingdata.state = 'ready'
        """, [resource_id], one=True)['count']


def check_run_ready(db, resource_id):
    """See if the given run has indicated it is ready.

    Returns the boolean, and the state
    """
    logger.info("Selecting run")
    res = query_db(db, """
        SELECT id, ready, state
        FROM runs
        WHERE
          run_id = %s
        """, [resource_id], one=True)
    is_ready, state = res['ready'], res['state']

    logger.info("Run with dbid={} is ready: {}".format(res['id'], is_ready))

    return is_ready, state


def get_project(db, resource_id):
    return query_db(db,
        """
        SELECT * from projects
        WHERE project_id = %s
        """,
        [resource_id], one=True)


def get_project_column(db, project_id, column):
    assert column in {'notes', 'schema', 'parties', 'result_type'}
    return query_db(db,
        """
        SELECT %s from projects
        WHERE project_id = %s
        """,
        [column, project_id], one=True)


def get_run_result(db, resource_id):
    """
    Return a Python dictionary mapping the index in A to
    the index in B.

    Note the response is mapping str -> int as both celery and
    postgres prefer keys to be strings.
    """
    return query_db(db,
        """
        SELECT result from run_results
        WHERE run = %s
        """,
        [resource_id], one=True)['result']


def get_paillier(db, run_id):
    """Given a run resource, return
    the Paillier public key and context.
    """
    paillier_id = query_db(db, """
                    SELECT paillier
                    FROM encrypted_permutation_masks
                    WHERE
                      run = %s
                    """, [run_id], one=True)['paillier']

    res = query_db(db, """
                    SELECT public_key, context
                    FROM paillier
                    WHERE
                      id = %s
                    """, [paillier_id], one=True)
    pk = res['public_key']
    cntx = res['context']

    return pk, cntx


def get_smaller_dataset_size_for_project(db, project_id):

    return query_db(db, """
        SELECT MIN(bloomingdata.size) as smaller
        FROM projects, dataproviders, bloomingdata
        WHERE
          bloomingdata.dp=dataproviders.id AND
          dataproviders.project=project.project_id AND
          projects.project_id=%s""", [project_id], one=True)['smaller']


def get_total_comparisons_for_mapping(db, project_id):
    """
    :return total number of comparisons for this project
    """

    res = query_db(db, """
        SELECT bloomingdata.size as rows
        from dataproviders, bloomingdata
        where
          bloomingdata.dp=dataproviders.id AND
          dataproviders.project=%s""", [project_id])

    if len(res) == 2:
        total_comparisons = res[0]['rows'] * res[1]['rows']
    else:
        total_comparisons = 'NA'

    return total_comparisons


def get_dataprovider_id(db, update_token):
    return query_db(db,
                    'select id from dataproviders WHERE token = %s',
                    [update_token], one=True)['id']


def get_filter_metadata(db, dp_id):
    """
    :return: The filename of the raw clks.
    """
    raw_json_filter = query_db(db, """
        SELECT file
        FROM bloomingdata
        WHERE
          dp = %s
        """, [dp_id], one=True)

    return raw_json_filter['file'].strip()


def get_number_of_hashes(db, dp_id):
    """
    :return: The size of the uploaded raw clks.
    """
    raw_json_filter = query_db(db, """
        SELECT size
        FROM bloomingdata
        WHERE
          dp = %s
        """, [dp_id], one=True)

    return raw_json_filter['size']


def get_permutation_result(db, dp_id, run_id):
    # Note doesn't include the mask, just the permutation for given dp
    return query_db(db,
        """
        SELECT permutation FROM permutations
        WHERE
          dp = %s AND
          run = %s

        """,
        [dp_id, run_id], one=True)['permutation']


def get_permutation_unencrypted_mask(db, project_id, run_id):
    return query_db(db,
        """SELECT raw from permutation_masks
        WHERE 
          project = %s AND
          run = %s
        """,
                    [project_id, run_id], one=True)['raw']


def get_permutation_encrypted_result_with_mask(db, mapping_resource_id, dp_id):
    # Query to fetch the full result for the 'permutation' result type
    raise NotImplementedError("Sorry. It is late.")
    return query_db(db,
        """
        SELECT
          permutations.permutation AS permutation,
          encrypted_permutation_masks.raw AS mask,
          paillier.context AS paillier_context
        FROM
          encrypted_permutation_masks,
          permutations,
          paillier
        WHERE
          encrypted_permutation_masks.paillier = paillier.id AND
          permutations.dp = %s AND
          mapping = %s

        """,
                    [dp_id, mapping_resource_id], one=True)


def get_similarity_scores_filename(db, run_id):
    return query_db(db,
        """
        SELECT file FROM similarity_scores
        WHERE
          run = %s

        """,
        [run_id], one=True)
