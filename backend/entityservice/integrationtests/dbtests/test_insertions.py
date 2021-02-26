import datetime

import psycopg2
from pytest import raises

from entityservice.database import insert_dataprovider, insert_encodings_into_blocks, insert_blocking_metadata, \
    get_project, get_encodingblock_ids, get_block_metadata, get_chunk_of_encodings, execute_select_query_in_binary,\
    get_encodings_of_multiple_blocks, update_run_mark_failure, get_run_status, insert_new_run

from entityservice.integrationtests.dbtests import _get_conn_and_cursor
from entityservice.models import Project
from entityservice.serialization import binary_format
from entityservice.tests.util import generate_bytes
from entityservice.utils import generate_code


class TestBinaryCopy:

    def test_execute_select_query_in_binary(self, conn, cur, prepopulated_binary_test_data):
        query = "select encoding from binary_test where id >= 10 and id < 20"
        res = list(execute_select_query_in_binary(cur, query))
        assert len(res) == 10
        for (i, original), stored in zip(prepopulated_binary_test_data[10:20], res):
            assert original == stored

    def test_execute_select_query_in_binary_empty(self, conn, cur, prepopulated_binary_test_data):
        query = "select encoding from binary_test where id < 0"
        res = list(execute_select_query_in_binary(cur, query))
        assert len(res) == 0


class TestInsertions:

    def _create_project(self):
        project = Project('groups', {}, name='', notes='', parties=2, uses_blocking=False)
        conn, cur = _get_conn_and_cursor()
        dp_ids = project.save(conn)
        return project, dp_ids

    def _create_project_and_dp(self):
        project, dp_ids = self._create_project()
        dp_id = dp_ids[0]
        dp_auth_token = project.update_tokens[0]

        conn, cur = _get_conn_and_cursor()
        # create a default block
        insert_blocking_metadata(conn, dp_id, {'1': 10000})
        conn.commit()

        assert len(dp_auth_token) == 48
        return project.project_id, project.result_token, dp_id, dp_auth_token

    def test_insert_project(self):
        before = datetime.datetime.utcnow()
        project, _ = self._create_project()
        assert len(project.result_token) == 48
        # check we can fetch the inserted project back from the database
        conn, cur = _get_conn_and_cursor()
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
        conn, cur = _get_conn_and_cursor()
        project_id = generate_code()
        dp_auth = generate_code()
        with raises(psycopg2.errors.ForeignKeyViolation):
            insert_dataprovider(cur, auth_token=dp_auth, project_id=project_id)

    def test_insert_many_clks(self):
        num_entities = 10_000
        encoding_size = 2048  # non default encoding size
        binary_formatter = binary_format(encoding_size)

        raw_data = [generate_bytes(encoding_size) for i in range(100)]
        encodings = [binary_formatter.pack(i, raw_data[i % 100]) for i in range(num_entities)]
        blocks = [['1'] for _ in range(num_entities)]

        project_id, project_auth_token, dp_id, dp_auth_token = self._create_project_and_dp()
        conn, cur = _get_conn_and_cursor()

        insert_encodings_into_blocks(conn, dp_id,
                                     block_names=blocks,
                                     entity_ids=list(range(num_entities)),
                                     encodings=encodings
                                     )
        conn.commit()

        block_names, block_ids, block_sizes = zip(*list(get_block_metadata(conn, dp_id)))

        assert len(block_names) == 1
        assert len(block_ids) == 1
        assert len(block_sizes) == 1
        assert block_names[0] == '1'
        assert block_sizes[0] == 10_000

        stored_encoding_ids = list(get_encodingblock_ids(conn, dp_id, block_ids[0]))

        assert len(stored_encoding_ids) == num_entities
        for stored_encoding_id, original_id in zip(stored_encoding_ids, range(num_entities)):
            assert stored_encoding_id == original_id

        stored_encodings = list(get_chunk_of_encodings(conn, dp_id, stored_encoding_ids, stored_binary_size=(encoding_size+4)))

        assert len(stored_encodings) == num_entities
        for stored_encoding, original_encoding in zip(stored_encodings, encodings):
            assert bytes(stored_encoding) == original_encoding

    def test_fetch_chunk(self):
        data = [generate_bytes(128) for _ in range(100)]
        project_id, project_auth_token, dp_id, dp_auth_token = self._create_project_and_dp()
        conn, cur = _get_conn_and_cursor()
        num_entities = 10_000
        blocks = [['1'] for _ in range(num_entities)]
        encodings = [data[i % 100] for i in range(num_entities)]

        insert_encodings_into_blocks(conn, dp_id,
                                     block_names=blocks,
                                     entity_ids=list(range(num_entities)),
                                     encodings=encodings
                                     )
        conn.commit()

        block_names, block_ids, block_sizes = zip(*list(get_block_metadata(conn, dp_id)))
        stored_encoding_ids = list(get_encodingblock_ids(conn, dp_id, block_ids[0], offset=10, limit=20))

        assert len(stored_encoding_ids) == 20
        for i, stored_encoding_id in enumerate(stored_encoding_ids):
            assert stored_encoding_id == i + 10

    def test_fetch_multiple_blocks(self):
        num_entities = 1000
        blocks = [[str(i)] for i in range(num_entities)]
        data = [generate_bytes(128) for _ in range(100)]
        encodings = [data[i % 100] for i in range(num_entities)]

        project, dp_ids = self._create_project()
        dp_id = dp_ids[0]
        dp_auth_token = project.update_tokens[0]
        conn, cur = _get_conn_and_cursor()
        # create a default block
        insert_blocking_metadata(conn, dp_id, {block[0]: 1 for block in blocks})
        conn.commit()

        insert_encodings_into_blocks(conn, dp_id,
                                     block_names=blocks,
                                     entity_ids=list(range(num_entities)),
                                     encodings=encodings
                                     )
        conn.commit()

        block_names, block_ids, block_sizes = zip(*list(get_block_metadata(conn, dp_id)))
        ret_encodings = list(get_encodings_of_multiple_blocks(conn, dp_id, block_ids))

        assert len(ret_encodings) == num_entities

        for enc1, enc2 in zip(encodings, ret_encodings):
            assert enc1 == enc2[2]

    def test_error_message(self):
        project, dp_ids = self._create_project()
        conn, cur = _get_conn_and_cursor()

        run_id = insert_new_run(db=conn, run_id=generate_code(), project_id=project.project_id, threshold=0.7,
                                name='integrationTest_run', notes='', type='testType')
        conn.commit()
        update_run_mark_failure(conn, run_id, 'integrational fail')
        conn.commit()
        status = get_run_status(conn, run_id)
        assert status['state'] == 'error'
        assert status['error_msg'] == 'integrational fail'
