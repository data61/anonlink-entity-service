from structlog import get_logger

from entityservice.tasks.comparing import _get_common_blocks, _create_work_packages
log = get_logger()


class TestCommonBlocks:
    # Unit test for _get_common_blocks

    def test_2p_get_common_blocks(self):
        dp_ids = [33, 34]
        dp_block_sizes = {33: {'1': 100}, 34: {'1': 100, '2': 100}}
        common_blocks = _get_common_blocks(dp_block_sizes, dp_ids)
        assert list(common_blocks) == [("1", (33, 34))]

    def test_3p_get_common_blocks(self):
        dp_ids = [1, 2, 3]
        dp_block_sizes = {1: {'1': 100}, 2: {'1': 100, '2': 100}, 3: {'1': 100, '2': 100}}
        common_blocks = set(_get_common_blocks(dp_block_sizes, dp_ids))

        assert ('1', (1, 2)) in common_blocks
        assert ('1', (1, 3)) in common_blocks
        assert ('1', (2, 3)) in common_blocks
        assert ('2', (2, 3)) in common_blocks
        assert len(common_blocks) == 4


class TestChunkingBlocks:

    def test_2p_single_chunked_block(self):
        dp_ids = [1, 2]
        dp_block_sizes = {
            1: {'1': 100},
            2: {'1': 100, '2': 100}}
        blocks = _get_common_blocks(dp_block_sizes, dp_ids)
        block_lookups = {1: {'1': 1}, 2: {'1': 1, '2': 2}}
        chunks = _create_work_packages(blocks, dp_block_sizes, dp_ids, log, block_lookups, chunk_size_aim=100)
        assert len(chunks) == 100
        for package in chunks:
            for chunk_pair in package:
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
        block_lookups = {1: {'1': 1}, 2: {'1': 1, '2': 2}, 3: {'1': 1, '2': 2}}
        blocks = _get_common_blocks(dp_block_sizes, dp_ids)
        chunks = _create_work_packages(blocks, dp_block_sizes, dp_ids, log, block_lookups, chunk_size_aim=100)
        # Case I: all blocks need to be chunked
        # Block 1 should create 100 chunks between dp combinations: 1:2, 1:3, and 2:3 for 300 chunks
        # Block 2 should create 100 chunks between 2:3
        assert len(chunks) == 300 + 100

        # Case II: each block fits into exactly one work package
        blocks = _get_common_blocks(dp_block_sizes, dp_ids)
        chunks = _create_work_packages(blocks, dp_block_sizes, dp_ids, log, block_lookups, chunk_size_aim=10000)
        assert len(chunks) == 4

        # Case III: all blocks fit into one work package
        blocks = _get_common_blocks(dp_block_sizes, dp_ids)
        chunks = _create_work_packages(blocks, dp_block_sizes, dp_ids, log, block_lookups, chunk_size_aim=40000)
        assert len(chunks) == 1

