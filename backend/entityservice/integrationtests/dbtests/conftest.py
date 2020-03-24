import pytest
import psycopg2

from entityservice.settings import Config as config


@pytest.fixture
def conn():
    db = config.DATABASE
    host = config.DATABASE_SERVER
    user = config.DATABASE_USER
    password = config.DATABASE_PASSWORD
    conn = psycopg2.connect(host=host, dbname=db, user=user, password=password)
    yield conn
    conn.close()

@pytest.fixture
def cur(conn):
    return conn.cursor()




@pytest.fixture()
def prepopulated_binary_test_data(conn, cur, num_bytes=4, num_rows=100):
    creation_sql = """
        DROP TABLE IF EXISTS binary_test;
        CREATE TABLE binary_test
            (
                id          integer not null,
                encoding    bytea   not null
            );"""
    cur.execute(creation_sql)
    conn.commit()

    # Add data using execute_values
    data = [(i, bytes([i % 128] * num_bytes)) for i in range(num_rows)]
    psycopg2.extras.execute_values(cur, """
    INSERT INTO binary_test (id, encoding) VALUES %s
    """, data)

    conn.commit()

    # quick check data is there
    cur.execute("select count(*) from binary_test")
    res = cur.fetchone()[0]
    assert res == num_rows

    cur.execute("select encoding from binary_test where id = 1")
    assert bytes(cur.fetchone()[0]) == data[1][1]

    yield data

    # delete test table
    deletion_sql = "drop table if exists binary_test cascade;"
    cur.execute(deletion_sql)
    conn.commit()
