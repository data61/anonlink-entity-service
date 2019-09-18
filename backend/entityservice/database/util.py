import time

import atexit
import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool
from flask import current_app
from structlog import get_logger

from entityservice.settings import Config as config

logger = get_logger()
connection_pool = None


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


def init_db(delay=0.5):
    """
    Initializes the database by creating the required tables.

    @param float delay: Number of seconds to wait before executing the SQL.
    """
    init_db_pool(1, 3)
    time.sleep(delay)
    with DBConn() as db:
        with current_app.open_resource('init-db-schema.sql', mode='r') as f:
            logger.warning("Initialising database")
            db.cursor().execute(f.read())


def init_db_pool(db_min_connections, db_max_connections):
    """
    Initializes the database connection pool required by the application to connect to the database.
    """
    db = config.DATABASE
    host = config.DATABASE_SERVER
    user = config.DATABASE_USER
    pw = config.DATABASE_PASSWORD

    global connection_pool
    if connection_pool is None:
        logger.info("Initialize the database connection pool. db: '%s', user: '%s', host: '%s'.", db, user, host)
        try:
            connection_pool = ThreadedConnectionPool(db_min_connections, db_max_connections, database=db, user=user, password=pw, host=host)
        except psycopg2.Error as e:
            logger.exception("Issue initializing the database connection pool. db: '%s', user: '%s', host: '%s'.",
                             db, user, host)
            raise ConnectionError("Issue initializing the database connection pool") from e
    else:
        logger.warning("The database connection pool has already been initialized.")


@atexit.register
def close_db_pool():
    """
    If a connection pool is available, close all its connections and set it to None.
    This method is always run at the exit of the application, to ensure that we free as much as possible
    the database connections.
    """
    global connection_pool
    logger.info("Close the database connection pool")
    if connection_pool is not None:
        connection_pool.closeall()
        connection_pool = None


class DBConn:
    """
    To connect to the database, it is preferred to use the pattern:
    with DBConn() as conn:
        ...
    It will ensure that the connection is taken from the connection pool return it to the pool
    when done. The pool must be initialized first via `init_db_pool()`.
    """

    def __init__(self):
        if connection_pool is None:
            raise ValueError("The database connection pool has not been initialized by the application."
                             " Use 'init_db_pool()' to initialise it.")

        logger.debug("Get a database connection from the pool.")
        try:
            self.conn = connection_pool.getconn()
        except psycopg2.Error as e:
            db = config.DATABASE
            host = config.DATABASE_SERVER
            user = config.DATABASE_USER
            logger.exception("Can't connect to database. db: '%s', user: '%s', host: '%s'.", db, user, host)
            raise ConnectionError("Issue connecting to database") from e

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc_val, traceback):
        result = True
        try:
            if not exc_type:
                self.conn.commit()
                for notice in self.conn.notices:
                    logger.debug(notice)
            else:
                # There was an exception in the DBConn body
                if isinstance(exc_type, psycopg2.Error):
                    # It was a Postgres exception
                    logger.warning(f"{exc_val.diag.severity} - {exc_val.pgerror}")
                # Note if we return True we swallow the exception, False we propagate it
                result = False
                self.conn.cancel()
        except Exception:
            logger.exception("Exception cleaning a connection before closing it or returning it to the pool.")
        finally:
            connection_pool.putconn(self.conn, close=False)
            self.conn = None
            return result


def execute_returning_id(cur, query, args):
    try:
        cur.execute(query, args)
    except psycopg2.Error as e:
        logger.exception("Error running db query")
        raise e
    query_result = cur.fetchone()
    if query_result is None:
        return None
    else:
        resource_id = query_result[0]
        return resource_id
