import psycopg2
from settings import Config as config
import logging

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

    host = config.DATABASE_SERVER
    user = config.DATABASE_USER
    pw = config.DATABASE_PASSWORD
    db = config.DATABASE

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


def insert_returning_id(cur, query, args):
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


def check_mapping_exists(db, resource_id):
    return query_db(db,
        'select count(*) from mappings WHERE resource_id = %s',
        [resource_id], one=True)['count'] == 1


def get_number_parties_uploaded(db, resource_id):
    return query_db(db, """
        SELECT COUNT(*)
        FROM dataproviders
        WHERE
          mapping = %s AND uploaded = TRUE
        """, [resource_id], one=True)['count']


def check_mapping_ready(db, resource_id):
    """See if the given mapping has indicated it is ready.
    Returns the boolean, the mappings database id, and the result type
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


def get_mapping_time(db, resource_id):
    return query_db(db, """
        SELECT (now() - time_added) as elapsed
        from mappings
        WHERE resource_id = %s""",
        [resource_id], one=True)['elapsed']


def get_dataprovider_id(db, update_token):
    return query_db(db,
                    'select id from dataproviders WHERE token = %s',
                    [update_token], one=True)['id']


def get_filter(db, dp_id):
    raw_json_filter = query_db(db, """
        SELECT raw
        FROM bloomingdata
        WHERE
          dp = %s
        """, [dp_id], one=True)['raw']

    return raw_json_filter


def get_permutation_result(db, dp_id):
    return query_db(db,
        """SELECT raw from permutationdata WHERE dp = %s""",
        [dp_id], one=True)['raw']

# Insertion Queries

def insert_mapping(cur, data, mapping, resource_id):
    return insert_returning_id(cur,
        """
        INSERT INTO mappings
        (resource_id, access_token, ready, schema, result_type)
        VALUES
        (%s, %s, false, %s, %s)
        RETURNING id;
        """,
        [
            resource_id,
            mapping.result_token,
            psycopg2.extras.Json(data['schema']),
            data['result_type']
        ])


def insert_permutation(cur, data, mapping, resource_id):
    return insert_returning_id(cur, """
            INSERT INTO mappings
            (resource_id, access_token, ready, schema, result_type, public_key, paillier_context)
            VALUES
            (%s, %s, false, %s, %s, %s, %s)
            RETURNING id;
            """,
            [
                resource_id, mapping.result_token,
                psycopg2.extras.Json(data['schema']),
                data['result_type'],
                psycopg2.extras.Json(data['public_key']),
                psycopg2.extras.Json(data['paillier_context'])
            ]
        )


def insert_dataprovider(cur, auth_token, mapping_db_id):
    return insert_returning_id(cur,
        """
        INSERT INTO dataproviders
        (mapping, token)
        VALUES
        (%s, %s)
        RETURNING id
        """,
        [mapping_db_id, auth_token]
        )


def insert_raw_filter_data(db, clks, dp_id, receipt_token):
    with db.cursor() as cur:
        logger.debug("Adding blooming data")
        cur.execute("""
            INSERT INTO bloomingdata
            (dp, token, raw)
            VALUES
            (%s, %s, %s)
            """,
                    [dp_id, receipt_token,
                     psycopg2.extras.Json(clks)])

        cur.execute("""
            UPDATE dataproviders
            SET uploaded = TRUE
            WHERE id = %s
            """, [dp_id])

    db.commit()


if __name__ == "__main__":

    db = connect_db()



