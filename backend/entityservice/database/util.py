import logging
import time

import psycopg2
from flask import current_app, g

from entityservice import database as db
from entityservice.settings import Config as config


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
    query_result = cur.fetchone()
    if query_result is None:
        return None
    else:
        resource_id = query_result[0]
        return resource_id



logger = logging.getLogger('db')


def get_db():
    """Opens a new database connection if there is none yet for the
    current application context.
    """
    conn = getattr(g, '_db', None)
    if conn is None:
        conn = g._db = db.connect_db()
    return conn