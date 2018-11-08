import logging
import time

import psycopg2
import psycopg2.extras
from flask import current_app, g
from structlog import get_logger
from entityservice import database as db
from entityservice.errors import DatabaseInconsistent, DBResourceMissing
from entityservice.settings import Config as config

logger = get_logger()


def query_db(db, query, args=(), one=False):
    """
    Queries the database and returns a list of dictionaries.

    https://flask-doc.readthedocs.org/en/latest/patterns/sqlite3.html#easy-querying
    """
    with db.cursor() as cur:
        logger.debug(f"Query: {query}")
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

    logger.debug("Database connection established")
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

    def __exit__(self, exc_type, exc_val, traceback):
        if not exc_type:
            self.conn.commit()
            for notice in self.conn.notices:
                logger.debug(notice)
            self.conn.close()
        else:
            # There was an exception in the DBConn body
            if isinstance(exc_type, psycopg2.Error):
                # It was a Postgres exception
                logger.warning(f"{exc_val.diag.severity} - {exc_val.pgerror}")
            # Note if we return True we swallow the exception, False we propagate it
            return False


def execute_returning_id(cur, query, args):
    try:
        cur.execute(query, args)
    except psycopg2.Error as e:
        logger.debug("Error running db query")
        logger.debug(e.diag.message_primary)
        raise e
    query_result = cur.fetchone()
    if query_result is None:
        return None
    else:
        resource_id = query_result[0]
        return resource_id


def get_db():
    """Opens a new database connection if there is none yet for the
    current flask application context.
    """
    conn = getattr(g, 'db', None)
    if conn is None:
        logger.debug("Caching a new database connection in application context")
        conn = g.db = db.connect_db()
    return conn
