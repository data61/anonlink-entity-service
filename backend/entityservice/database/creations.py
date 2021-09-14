from structlog import get_logger

logger = get_logger()


def create_partitions(conn, dp_ids):
    with conn.cursor() as cur:
        for dp_id in dp_ids:
            log = logger.bind(dp_id=dp_id)
            log.info("try to acquire lock from db")
            sql = "SELECT pg_advisory_xact_lock(42)"
            cur.execute(sql)
            log.info("got the lock, let's go.")
            sql = f"CREATE TABLE encodings_{dp_id} (LIKE encodings INCLUDING DEFAULTS INCLUDING CONSTRAINTS);"
            cur.execute(sql)
            sql = f"ALTER TABLE encodings ATTACH PARTITION encodings_{dp_id} FOR VALUES IN ({dp_id});"
            cur.execute(sql)
            log.info(f"created partition encodings_{dp_id}")
            sql = f"CREATE TABLE encodingblocks_{dp_id} (LIKE encodingblocks INCLUDING DEFAULTS INCLUDING CONSTRAINTS);"
            cur.execute(sql)
            sql = f"ALTER TABLE encodingblocks ATTACH PARTITION encodingblocks_{dp_id} FOR VALUES IN ({dp_id});"
            cur.execute(sql)
            log.info(f"created partition encodingblocks_{dp_id}")
