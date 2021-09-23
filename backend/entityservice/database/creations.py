from structlog import get_logger

logger = get_logger()


def create_partitions(conn, dp_id):
    log = logger.bind(dp_id=dp_id)
    log.info(f"create partitions encodings_{dp_id} and encodingblocks_{dp_id}")
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE TABLE encodings_{dp_id} (LIKE encodings INCLUDING DEFAULTS INCLUDING CONSTRAINTS) "
                f"WITH (autovacuum_enabled = false)")
            cur.execute(
                f"CREATE TABLE encodingblocks_{dp_id} (LIKE encodingblocks INCLUDING DEFAULTS INCLUDING CONSTRAINTS) "
                f"WITH (autovacuum_enabled = false)")
    with conn:
        with conn.cursor() as cur:
            log.info(f'attach encodingblocks partition {dp_id}')
            cur.execute(f"ALTER TABLE encodingblocks ATTACH PARTITION encodingblocks_{dp_id} FOR VALUES IN ({dp_id})")
    with conn:
        with conn.cursor() as cur:
            log.info(f'attach encodings partition {dp_id}')
            cur.execute(f"ALTER TABLE encodings ATTACH PARTITION encodings_{dp_id} FOR VALUES IN ({dp_id})")
    log.info("partitions created.")
