from structlog import get_logger

from entityservice.tasks.comparing import _get_common_blocks, _create_work_chunks
log = get_logger()


class TestCommonBlocks:
    # Unit test for _get_common_blocks

    def test_2p_get_common_blocks(self):
        dp_ids = [33, 34]
        dp_block_sizes = {33: {'1': 100}, 34: {'1': 100, '2': 100}}
        common_blocks = _get_common_blocks(dp_block_sizes, dp_ids)
        assert common_blocks == {"1": [(33, 34)]}

    def test_3p_get_common_blocks(self):
        dp_ids = [1, 2, 3]
        dp_block_sizes = {1: {'1': 100}, 2: {'1': 100, '2': 100}, 3: {'1': 100, '2': 100}}
        common_blocks = _get_common_blocks(dp_block_sizes, dp_ids)
        assert '1' in common_blocks
        assert len(common_blocks['1']) == 3
        block_1_set = set(common_blocks['1'])
        # Should have (1, 2), (1, 3), (2, 3)
        for dpcombo in [(1, 2), (1, 3), (2, 3)]:
            assert dpcombo in block_1_set

        assert '2' in common_blocks
        assert len(common_blocks['2']) == 1
        assert common_blocks['2'][0] == (2, 3)


class TestChunkingBlocks:

    def test_2p_single_chunked_block(self):
        dp_ids = [1, 2]
        dp_block_sizes = {
            1: {'1': 100},
            2: {'1': 100, '2': 100}}
        blocks = {"1": [(1, 2)]}

        chunks = _create_work_chunks(blocks, dp_block_sizes, dp_ids, log, 100)
        assert len(chunks) == 100
        for chunk_pair in chunks:
            for c in chunk_pair:
                assert "range" in c
                lower, upper = c['range']
                assert lower < upper
                assert upper - lower <= 10
                assert "block_id" in c
                assert "datasetIndex" in c
                assert "dataproviderId" in c

    def test_basic_3p(self):
        dp_ids = [1, 2, 3]
        dp_block_sizes = {
            1: {'1': 100},
            2: {'1': 100, '2': 100},
            3: {'1': 100, '2': 100},
        }
        blocks = _get_common_blocks(dp_block_sizes, dp_ids)
        chunks = _create_work_chunks(blocks, dp_block_sizes, dp_ids, log, 100)
        # Block 1 should create 100 chunks between dp combinations: 1:2, 1:3, and 2:3 for 300 chunks
        # Block 2 should create 100 chunks between 2:3
        assert len(chunks) == 300 + 100

