from structlog import get_logger

logger = get_logger()


def create_partitions(conn, dp_ids):
    with conn:
        with conn.cursor() as cur:
            for dp_id in dp_ids:
                log = logger.bind(dp_id=dp_id)
                log.debug(f"create tables encodings_{dp_id} and ecodingblocks_{dp_id}")
                cur.execute(
                    f"CREATE TABLE encodings_{dp_id} (LIKE encodings INCLUDING DEFAULTS INCLUDING CONSTRAINTS) "
                    f"WITH (autovacuum_enabled = false)")
                cur.execute(f"CREATE TABLE encodingblocks_{dp_id} "
                            f"(LIKE encodingblocks INCLUDING DEFAULTS INCLUDING CONSTRAINTS)")
                log.debug('created.')
    with conn:
        with conn.cursor() as cur:
            for dp_id in dp_ids:
                log = logger.bind(dp_id=dp_id)
                log.info(f'attach encodingblocks partition {dp_id}')
                cur.execute(f"ALTER TABLE encodingblocks ATTACH PARTITION encodingblocks_{dp_id} FOR VALUES IN ({dp_id})")
                log.debug('attached')
    with conn:
        with conn.cursor() as cur:
            for dp_id in dp_ids:
                log = logger.bind(dp_id=dp_id)
                log.info(f'attach encodings partition {dp_id}')
                cur.execute(f"ALTER TABLE encodings ATTACH PARTITION encodings_{dp_id} FOR VALUES IN ({dp_id})")
                log.debug('attached')
    # with conn:
    #     with conn.cursor() as cur:
    #         for dp_id in dp_ids:
    #             log = logger.bind(dp_id=dp_id)
    #             log.info("try to acquire lock 42 from db for partition creation")
    #             cur.execute("SELECT pg_advisory_xact_lock(42)")
    #             log.info("got the lock, let's go.")
    #             cur.execute(f"ALTER TABLE encodingblocks ATTACH PARTITION encodingblocks_{dp_id} FOR VALUES IN ({dp_id})")
    #             cur.execute(f"ALTER TABLE encodings ATTACH PARTITION encodings_{dp_id} FOR VALUES IN ({dp_id})")
    #             log.info(f"created partitions encodingblocks_{dp_id} and encodings_{dp_id}")
    #             log.info('freeing lock 42')
