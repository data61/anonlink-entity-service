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


# Handy shared database queries

def check_mapping_ready(db, resource_id):
    """See if the given mapping has indicated it is ready.
    Returns the boolean and the mappings database id
    """
    logger.info("Selecting mapping resource")
    res = query_db(db, """
        SELECT id, ready
        FROM mappings
        WHERE
          resource_id = %s
        """, [resource_id], one=True)
    is_ready = res['ready']

    logger.info("Database mapping with id={} is ready: {}".format(res['id'], is_ready))

    return is_ready, res['id']


def get_filter(db, dp_id):
    raw_json_filter = query_db(db, """
        SELECT raw
        FROM bloomingdata
        WHERE
          dp = %s
        """, [dp_id], one=True)['raw']

    return raw_json_filter


if __name__ == "__main__":

    db = connect_db()



