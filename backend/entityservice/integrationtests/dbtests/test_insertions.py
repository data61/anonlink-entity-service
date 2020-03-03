import datetime
import time

import psycopg2
from pytest import raises

from entityservice.database import insert_dataprovider, insert_new_project, \
    insert_encodings_into_blocks, insert_blocking_metadata, get_project, get_encodingblock_ids
from entityservice.models import Project
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
        project, dp_ids = self._create_project()
        dp_id = dp_ids[0]
        dp_auth_token = project.update_tokens[0]

        conn, cur = self._get_conn_and_cursor()
        # create a default block
        insert_blocking_metadata(conn, dp_id, {'1': 99})
        conn.commit()

        assert len(dp_auth_token) == 48
        return project.project_id, project.result_token, dp_id, dp_auth_token

    def _create_project(self):
        project = Project('groups', {}, name='', notes='', parties=2, uses_blocking=False)
        conn, cur = self._get_conn_and_cursor()
        dp_ids = project.save(conn)
        return project, dp_ids

    def test_insert_project(self):
        before = datetime.datetime.now()
        project, _ = self._create_project()
        assert len(project.result_token) == 48
        # check we can fetch the inserted project back from the database
        conn, cur = self._get_conn_and_cursor()
        project_response = get_project(conn, project.project_id)
        assert 'time_added' in project_response
        assert project_response['time_added'] - before >= datetime.timedelta(seconds=0)
        assert not project_response['marked_for_deletion']
        assert not project_response['uses_blocking']
        assert project_response['parties'] == 2
        assert project_response['notes'] == ''
        assert project_response['name'] == ''
        assert project_response['result_type'] == 'groups'
        assert project_response['schema'] == {}
        assert project_response['encoding_size'] is None

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
        blocks = [['1'] for _ in range(num_entities)]
        encodings = [data[i % 100] for i in range(num_entities)]
        start_time = time.perf_counter()
        insert_encodings_into_blocks(conn, dp_id,
                                     block_ids=blocks,
                                     encoding_ids=list(range(num_entities)),
                                     encodings=encodings
                                     )
        end_time = time.perf_counter()
        elapsed_time = end_time - start_time
        # This takes ~0.5s using docker compose on a ~5yo desktop.
        # If the database is busy - e.g. if you're running integration
        # tests and e2e tests at the same time, this assertion could fail.
        assert elapsed_time < 2

        stored_encoding_ids = list(get_encodingblock_ids(conn, dp_id, '1'))
        fetch_time = time.perf_counter() - end_time
        # retrieval of encoding ids should be much faster than insertion
        assert fetch_time < elapsed_time

        assert len(stored_encoding_ids) == num_entities
        for stored_encoding_id, original in zip(stored_encoding_ids, range(num_entities)):
            assert stored_encoding_id == original

        # TODO fetch binary encodings and verify against uploaded
