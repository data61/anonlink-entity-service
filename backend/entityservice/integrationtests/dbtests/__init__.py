import psycopg2

from entityservice.settings import Config as config


def _get_conn_and_cursor():
    db = config.DATABASE
    host = config.DATABASE_SERVER
    user = config.DATABASE_USER
    password = config.DATABASE_PASSWORD
    conn = psycopg2.connect(host=host, dbname=db, user=user, password=password)
    cursor = conn.cursor()
    return conn, cursor
