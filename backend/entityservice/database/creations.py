from structlog import get_logger


logger = get_logger()


def create_data_tables(conn, dp_ids):
    log = logger.bind(dp_ids=dp_ids)
    log.info(f'creating encodings and encodingblocks tables for dps: {dp_ids}')

    with conn.cursor() as cur:
        for dp_id in dp_ids:
            cur.execute(f"""
                CREATE TABLE encodings_{dp_id} (
                    encoding_id BIGSERIAL NOT NULL, 
                    encoding BYTEA NOT NULL, 
                    PRIMARY KEY (encoding_id)
                ) WITH (autovacuum_enabled = false);
                """)
            cur.execute(f"""
                CREATE TABLE encodingblocks_{dp_id} (
                    entity_id INTEGER, 
                    encoding_id BIGINT, 
                    block_id INTEGER, 
                    FOREIGN KEY(encoding_id) REFERENCES encodings_{dp_id} (encoding_id)
                ) WITH (autovacuum_enabled = false);
            """)
