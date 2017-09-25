import time
import logging
from datetime import timedelta
import psycopg2
from flask import current_app
from settings import Config as config
logger = logging.getLogger('db')


def query_db(db, query, args=(), one=False):
    """
    Queries the database and returns a list of dictionaries.

    https://flask-doc.readthedocs.org/en/latest/patterns/sqlite3.html#easy-querying
    """
    with db.cursor() as cur:
        cur.execute(query, args)
        rv = [dict((cur.description[idx][0], value)
                   for idx, value in enumerate(row)) for row in cur.fetchall()]
    return (rv[0] if rv else None) if one else rv


def connect_db():

    db = config.DATABASE
    host = config.DATABASE_SERVER
    user = config.DATABASE_USER
    pw = config.DATABASE_PASSWORD

    logger.debug("Trying to connect to postgres db")
    # We nest the try/except blocks to allow one re-attempt with defaults
    try:
        try:
            conn = psycopg2.connect(database=db, user=user, password=pw, host=host)
        except psycopg2.OperationalError:
            logger.warning("warning connecting to default postgres db")
            conn = psycopg2.connect(database='postgres', user=user, password=pw, host=host)

    except psycopg2.Error:
        logger.warning("Can't connect to database")
        raise ConnectionError("Issue connecting to database")

    return conn


def init_db(delay=0.5):
    """Initializes the database."""
    time.sleep(delay)
    db = connect_db()
    with current_app.open_resource('init-db-schema.sql', mode='r') as f:
        logger.warning("Initialising database")
        db.cursor().execute(f.read())
    db.commit()


class DBConn:
    def __enter__(self):
        self.conn = connect_db()
        return self.conn

    def __exit__(self, *args):
        self.conn.commit()
        self.conn.close()


def execute_returning_id(cur, query, args):
    """

    """
    cur.execute(query, args)
    resource_id = cur.fetchone()[0]
    return resource_id


# Shared database queries

def check_mapping_auth(db, resource_id, results_token):
    return query_db(db, """
        select count(*) from mappings
        WHERE
          resource_id = %s AND
          access_token = %s
        """, [resource_id, results_token], one=True)['count'] == 1


def check_update_auth(db, update_token):
    return get_dataprovider_id(db, update_token) is not None


def select_dataprovider_id(db, mapping_resource_id, receipt_token):
    """
    Given a receipt token get the id of the matching data provider.
    Returns None if token is incorrect.
    """
    res = query_db(db, """
        select dp from dataproviders, bloomingdata, mappings
        WHERE
          bloomingdata.dp = dataproviders.id AND
          dataproviders.mapping = mappings.id AND
          mappings.resource_id = %s AND
          bloomingdata.token = %s
        """, [mapping_resource_id, receipt_token], one=True)

    logger.debug("Looking up data provider with auth. {}".format(res))
    return res['dp'] if res is not None else None


def get_dataprovider_ids(db, mapping_resource_id):
    # Get the data provider IDS given a mapping resource
    dp_ids = list(map(lambda d: d['id'], query_db(db, """
            SELECT dataproviders.id
            FROM dataproviders, mappings
            WHERE
              mappings.resource_id = %s AND
              dataproviders.uploaded = TRUE AND
              mappings.id = dataproviders.mapping
            """, [mapping_resource_id])))
    return dp_ids


def check_mapping_exists(db, resource_id):
    return query_db(db,
        'select count(*) from mappings WHERE resource_id = %s',
        [resource_id], one=True)['count'] == 1


def get_latest_rate(db):
    res = query_db(db, 'select ts, rate from metrics order by ts desc limit 1', one=True)
    if res is None:
        # Just to avoid annoying divide by zero errors return a low rate
        # if the true value is unknown
        current_rate = 1
    else:
        current_rate = res['rate']

    return current_rate


def get_number_parties_uploaded(db, resource_id):
    return query_db(db, """
        SELECT COUNT(*)
        FROM dataproviders, bloomingdata
        WHERE
          mapping = %s AND
          bloomingdata.dp = dataproviders.id AND
          dataproviders.uploaded = TRUE AND
          bloomingdata.state = 'ready'
        """, [resource_id], one=True)['count']


def check_mapping_ready(db, resource_id):
    """See if the given mapping has indicated it is ready.
    Returns the boolean, the mappings database id, the result type
    """
    logger.info("Selecting mapping resource")
    res = query_db(db, """
        SELECT id, ready, result_type
        FROM mappings
        WHERE
          resource_id = %s
        """, [resource_id], one=True)
    is_ready = res['ready']

    logger.info("Database mapping with id={} is ready: {}".format(res['id'], is_ready))

    return is_ready, res['id'], res['result_type']


def get_mapping(db, resource_id):
    return query_db(db,
        """
        SELECT * from mappings
        WHERE resource_id = %s
        """,
        [resource_id], one=True)


def get_mapping_result(db, resource_id):
    """
    Return a Python dictionary mapping the index in A to
    the index in B.

    Note the response is mapping str -> int as both celery and
    postgres prefer keys to be strings.
    """
    return query_db(db,
        """
        SELECT result from mapping_results
        WHERE mapping = %s
        """,
        [resource_id], one=True)['result']


def get_paillier(db, resource_id):
    """Given a mapping resource, return
    the Paillier public key and context.
    """
    paillier_id = query_db(db, """
                    SELECT paillier
                    FROM encrypted_permutation_masks
                    WHERE
                      mapping = %s
                    """, [resource_id], one=True)['paillier']

    res = query_db(db, """
                    SELECT public_key, context
                    FROM paillier
                    WHERE
                      id = %s
                    """, [paillier_id], one=True)
    pk = res['public_key']
    cntx = res['context']

    return pk, cntx


def delete_mapping(db, resource_id):
    mapping = get_mapping(db, resource_id)
    mapping_id = mapping['id']
    result_type = mapping['result_type']

    with db.cursor() as cur:
        logger.info("Beginning db transaction to remove a mapping resource")
        dps = query_db(db, """
            SELECT id
            FROM dataproviders
            WHERE mapping = %s
            """, [mapping_id])

        for dp in dps:
            cur.execute("""
                DELETE FROM bloomingdata
                WHERE dp = %s
                """, [dp['id']])

            if result_type != 'mapping':
                cur.execute("""
                    DELETE FROM permutations
                    WHERE dp = %s
                    """, [dp['id']])
        if result_type != 'mapping':
            cur.execute("""
                DELETE FROM permutation_masks
                WHERE mapping = %s
                """, [resource_id])

        if result_type == "permutation":
            paillier_id = execute_returning_id(cur, """
                DELETE FROM encrypted_permutation_masks
                WHERE mapping = %s
                RETURNING paillier
                """, [resource_id])

            cur.execute("""
                DELETE FROM paillier
                WHERE id = %s
                """, [paillier_id])

        if result_type == "similarity_scores":
            cur.execute("""
                DELETE FROM similarity_scores
                WHERE mapping = %s
                """, [resource_id])

        cur.execute("""
            DELETE FROM dataproviders
            WHERE mapping = %s
            """, [mapping_id])

        cur.execute("""
            DELETE FROM mapping_results
            WHERE mapping = %s
            """, [resource_id])

        cur.execute("""
            DELETE FROM mappings
            WHERE resource_id = %s
            """, [resource_id])

    logger.info("Committing removal of mapping resource")
    db.commit()


def get_mapping_time(db, resource_id):
    res = query_db(db, """
        SELECT (now() - time_started) as elapsed
        from mappings
        WHERE resource_id = %s""",
        [resource_id], one=True)['elapsed']

    return timedelta(seconds=0) if res is None else res


def get_smaller_dataset_size_for_mapping(db, resource_id):

    return query_db(db, """
        SELECT MIN(bloomingdata.size) as smaller
        FROM mappings, dataproviders, bloomingdata
        WHERE
          bloomingdata.dp=dataproviders.id AND
          dataproviders.mapping=mappings.id AND
          mappings.resource_id=%s""", [resource_id], one=True)['smaller']



def get_total_comparisons_for_mapping(db, resource_id):
    """
    :return total number of comparisons for this job
    """

    res = query_db(db, """
        SELECT bloomingdata.size as rows
        from mappings, dataproviders, bloomingdata
        where
          bloomingdata.dp=dataproviders.id AND
          dataproviders.mapping=mappings.id AND
          mappings.resource_id=%s""", [resource_id])

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
    :return: The filename of the raw clks and a list of popcounts for given data provider
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


def get_permutation_result(db, dp_id):
    # Note doesn't include the mask, just the permutation for given dp
    return query_db(db,
        """
        SELECT permutation FROM permutations
        WHERE
          dp = %s

        """,
        [dp_id], one=True)['permutation']


def get_permutation_unencrypted_mask(db, mapping_resource_id):
    return query_db(db,
        """SELECT raw from permutation_masks
        WHERE mapping = %s
        """,
        [mapping_resource_id], one=True)['raw']


def get_permutation_encrypted_result_with_mask(db, mapping_resource_id, dp_id):
    # Query to fetch the full result for the 'permutation' result type
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


def get_similarity_scores_filename(db, resource_id):
    return query_db(db,
        """
        SELECT file FROM similarity_scores
        WHERE
          mapping = %s

        """,
        [resource_id], one=True)


# Insertion Queries


def insert_comparison_rate(cur, rate):
    return execute_returning_id(cur, """
        INSERT INTO metrics
        (rate) VALUES (%s)
        RETURNING id;
        """, [rate])


def insert_mapping(cur, result_type, schema, threshold, mapping, resource_id):
    return execute_returning_id(cur,
        """
        INSERT INTO mappings
        (resource_id, access_token, ready, schema, result_type, threshold)
        VALUES
        (%s, %s, false, %s, %s, %s)
        RETURNING id;
        """,
                                [
            resource_id,
            mapping.result_token,
            psycopg2.extras.Json(schema),
            result_type,
            threshold
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


def insert_empty_encrypted_mask(cur, resource_id, pid):
    return execute_returning_id(cur, """
            INSERT INTO encrypted_permutation_masks
            (mapping, paillier)
            VALUES
            (%s, %s)
            RETURNING id;
            """,
            [
                resource_id,
                pid
            ]
        )


def insert_dataprovider(cur, auth_token, mapping_db_id):
    return execute_returning_id(cur,
        """
        INSERT INTO dataproviders
        (mapping, token)
        VALUES
        (%s, %s)
        RETURNING id
        """,
        [mapping_db_id, auth_token]
      )


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


def update_mapping_chunk(db, resource_id, chunk_size):
    with db.cursor() as cur:
        cur.execute("""
            UPDATE mappings
            SET
              chunk_size = %s
            WHERE
              resource_id = %s
            """,
            [
                chunk_size,
                resource_id
             ])
    db.commit()
