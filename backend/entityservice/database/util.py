import time
from io import BytesIO
from typing import Iterable

import atexit
import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool
from flask import current_app
from structlog import get_logger
from tenacity import retry, wait_random_exponential, retry_if_exception_type, stop_after_delay

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


@retry(wait=wait_random_exponential(multiplier=1, max=60),
       retry=(retry_if_exception_type(psycopg2.OperationalError) | retry_if_exception_type(ConnectionError)),
       stop=stop_after_delay(120))
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
        logger.info("Initializing the database connection pool. db: '%s', user: '%s', host: '%s'.", db, user, host)
        try:
            connection_pool = ThreadedConnectionPool(db_min_connections, db_max_connections, database=db, user=user,
                                                     password=pw, host=host)
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
    This method is always run at the exit of the application, to ensure that we free
    the database connections when possible.
    """
    global connection_pool
    logger.info("Closing the database connection pool")
    if connection_pool is not None:
        connection_pool.closeall()
        connection_pool = None


class DBConn:
    """
    To connect to the database, it is preferred to use the pattern:
    with DBConn() as conn:
        ...

    This ensures that the connection is taken from the connection pool and returned to the pool
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


def binary_format(stream: BytesIO):
    """
    parse binary format of Postgresql. This is a generator which yields one row at a time.
    :param stream: a byte stream containing the result of a binary sql query.
    :return: yield row of the result
    """
    stream.seek(0)
    # Need to read/remove the Postgres Binary Header, Trailer, and the per tuple info
    # https://www.postgresql.org/docs/current/sql-copy.html
    header = stream.read(15)
    assert header == b'PGCOPY\n\xff\r\n\x00\x00\x00\x00\x00', "Invalid Binary Format"
    header_extension = stream.read(4)
    assert header_extension == b'\x00\x00\x00\x00', "Need to implement skipping postgres binary header extension"
    # now iterate over the rows
    while True:
        num_elements = int.from_bytes(stream.read(2), byteorder='big')  # apparently bytes are in network byte order
        if num_elements == 65535:   # we reached the end of the results. Binary trailer of \xff\xff
            return
        row_values = []
        for i in range(num_elements):
            size = int.from_bytes(stream.read(4), byteorder='big')
            el_value = stream.read(size)
            row_values.append(el_value)
        if num_elements == 1:
            yield row_values[0]
        else:
            yield row_values


def compute_encoding_ids(entity_ids: Iterable[int], dp_id: int):
    """ compute unique encoding ids for given entity ids
    The user provides entity ids. Although unique for the user, different user can have the same entity ids.
    However, we want to use the id as a unique identifier for the encoding in the database. Thus, we create a
    unique number here. """
    dp_offset = dp_id << 32
    return [dp_offset + entity_id for entity_id in entity_ids]
