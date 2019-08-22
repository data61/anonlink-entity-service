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
    time.sleep(delay)
    with DBConn() as db:
        with current_app.open_resource('init-db-schema.sql', mode='r') as f:
            logger.warning("Initialising database")
            db.cursor().execute(f.read())


def init_db_pool():
    db = config.DATABASE
    host = config.DATABASE_SERVER
    user = config.DATABASE_USER
    pw = config.DATABASE_PASSWORD
    db_max_connections = config.DATABASE_MAX_CONNECTIONS

    global connection_pool
    if connection_pool is None:
        logger.info("Initialize the database connection pool.", database=db, user=user, password=pw, host=host)
        try:
            connection_pool = ThreadedConnectionPool(1, db_max_connections, database=db, user=user, password=pw, host=host)
        except psycopg2.Error as e:
            logger.warning("Can't connect to database")
            raise ConnectionError("Issue connecting to database") from e
    else:
        logger.warning("The connection pool has already been initialized.")


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
    It will ensure that the connection is either taken from the connection pool if available and return it to the pool
    when done, or it will create a single connection which is closed when done.
    """

    return_to_pool = True

    def __init__(self, conn=None):
        if conn is None:
            if connection_pool is not None:
                logger.debug("Get a database connection from the pool.")
                try:
                    self.conn = connection_pool.getconn()
                except psycopg2.Error:
                    logger.warning("Can't connect to database")
                    raise ConnectionError("Issue connecting to database")
            else:
                logger.debug("Get a database connection without a pool.")
                self.__connect_db()
                self.return_to_pool = False

        else:
            # Not sure where the connection is coming from...
            logger.debug("Use our own connection.")
            self.conn = conn
            self.return_to_pool = False

    def __enter__(self):
        return self.conn

    def __connect_db(self):
        db = config.DATABASE
        host = config.DATABASE_SERVER
        user = config.DATABASE_USER
        pw = config.DATABASE_PASSWORD

        logger.info("Trying to connect to database.", database=db, user=user, host=host)
        try:
            self.conn = psycopg2.connect(database=db, user=user, password=pw, host=host)
        except psycopg2.Error:
            logger.warning("Can't connect to database")
            raise ConnectionError("Issue connecting to database")

        logger.debug("Database connection established")

    def __exit__(self, exc_type, exc_val, traceback):
        try:
            result = True
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
            return result
        except Exception as e:
            logger.warning("Exception cleaning a connection before closing it or returning it to the pool.", e)
        finally:
            if self.return_to_pool:
                connection_pool.putconn(self.conn, close=False)
            else:
                logger.debug("Close the database connection.")
                self.conn.close()


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
