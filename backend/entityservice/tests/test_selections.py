import pytest
from unittest.mock import MagicMock

from entityservice.database.selections import get_encodings_of_multiple_blocks


class TestGetEncodingsOfMultipleBlocksQueryBuilding:
    def test_rejects_non_integer_block_id(self):
        """block_ids end up string-formatted straight into SQL (COPY doesn't take bound
        params), so a non-integer value must be rejected before it reaches the query
        instead of being interpolated as-is."""
        db = MagicMock()
        malicious_block_ids = ["1'); DROP TABLE encodings; --"]

        with pytest.raises(ValueError):
            list(get_encodings_of_multiple_blocks(db, dp_id=1, block_ids=malicious_block_ids))

    def test_rejects_non_integer_dp_id(self):
        db = MagicMock()

        with pytest.raises(ValueError):
            list(get_encodings_of_multiple_blocks(db, dp_id="1 OR 1=1", block_ids=[1, 2]))

    def test_accepts_integer_ids(self):
        db = MagicMock()
        fake_cursor = db.cursor.return_value

        def fake_copy_expert(query, stream):
            # minimal empty PGCOPY binary result (header + header extension + trailer)
            stream.write(b'PGCOPY\n\xff\r\n\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xff')

        fake_cursor.copy_expert.side_effect = fake_copy_expert

        # exhaust the generator without touching a real database
        rows = list(get_encodings_of_multiple_blocks(db, dp_id=1, block_ids=[1, 2, 3]))

        assert rows == []
        assert fake_cursor.copy_expert.called
