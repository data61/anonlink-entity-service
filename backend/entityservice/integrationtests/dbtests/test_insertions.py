import time

import psycopg2
from pytest import raises

from entityservice.database import insert_dataprovider, insert_new_project, \
    insert_encodings_into_blocks, insert_blocking_metadata, get_project, get_encodingblock_ids
from entityservice.tests.util import generate_bytes
from entityservice.utils import generate_code
from entityservice.settings import Config as config


class TestInsertions:

    def _get_conn_and_cursor(self):
        db = config.DATABASE
        host = config.DATABASE_SERVER
        user = config.DATABASE_USER
        password = config.DATABASE_PASSWORD
        conn = psycopg2.connect(host=host, dbname=db, user=user, password=password)
        cursor = conn.cursor()
        return conn, cursor

    def _create_project_and_dp(self):
        project_id, project_auth_token = self._create_project()
        dp_auth_token = generate_code()
        conn, cur = self._get_conn_and_cursor()
        dp_id = insert_dataprovider(cur, auth_token=dp_auth_token, project_id=project_id)
        conn.commit()
        # We create a default block too
        insert_blocking_metadata(conn, dp_id, {'1': 99})
        conn.commit()

        assert len(dp_auth_token) == 48
        return project_id, project_auth_token, dp_id, dp_auth_token

    def _create_project(self):
        project_id = generate_code()
        project_auth_token = generate_code()

        conn, cur = self._get_conn_and_cursor()
        insert_new_project(cur, 'groups', '{}', project_auth_token, project_id,
                           num_parties=2, name='', notes='', uses_blocking=False)
        conn.commit()
        return project_id, project_auth_token

    def test_insert_project(self):
        project_id, project_auth_token = self._create_project()
        assert len(project_auth_token) == 48
        # check we can fetch the inserted project back from the database
        conn, cur = self._get_conn_and_cursor()
        project = get_project(conn, project_id)
        assert 'time_added' in project
        assert not project['marked_for_deletion']
        assert not project['uses_blocking']

    def test_insert_project_and_dp(self):
        project_id, project_auth_token, dp_id, dp_auth_token = self._create_project_and_dp()
        assert len(dp_auth_token) == 48

    def test_insert_dp_no_project_fails(self):
        conn, cur = self._get_conn_and_cursor()
        project_id = generate_code()
        dp_auth = generate_code()
        with raises(psycopg2.errors.ForeignKeyViolation):
            insert_dataprovider(cur, auth_token=dp_auth, project_id=project_id)

    def test_insert_many_clks(self):
        data = [generate_bytes(128) for _ in range(100)]
        project_id, project_auth_token, dp_id, dp_auth_token = self._create_project_and_dp()
        conn, cur = self._get_conn_and_cursor()

        num_entities = 10_000
        start_time = time.perf_counter()

        blocks = [['1'] for _ in range(num_entities)]
        encodings = [data[i % 100] for i in range(num_entities)]

        insert_encodings_into_blocks(conn, dp_id,
                                     block_ids=blocks,
                                     encoding_ids=list(range(num_entities)),
                                     encodings=encodings
                                     )

        end_time = time.perf_counter()
        elapsed_time = end_time - start_time
        assert elapsed_time < 1

        stored_encodings = list(get_encodingblock_ids(conn, dp_id, '1'))
        assert len(stored_encodings) == num_entities
        fetch_time = time.perf_counter() - end_time
        # retrieval should be faster than insertion
        assert fetch_time < elapsed_time
