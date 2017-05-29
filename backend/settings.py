#!/usr/bin/env python3.4
"""
Config shared between the application backend and the celery workers.
"""
import os
import logging


class Config(object):
    """
    Hard coded default configuration which can be overwritten with environment variables
    """

    DEBUG = os.environ.get("DEBUG", "false") == "true"

    LOGFILE = os.environ.get("LOGFILE", None)
    fileFormat = logging.Formatter('%(asctime)-15s %(name)-12s %(levelname)-8s: %(message)s')
    consoleFormat = logging.Formatter('%(asctime)-10s %(levelname)-8s %(message)s',
                                      datefmt="%H:%M:%S")

    REDIS_SERVER = os.environ.get('REDIS_SERVER', 'redis')
    REDIS_PASSWORD = os.environ.get('REDIS_PASSWORD', '')

    MINIO_SERVER = os.environ.get('MINIO_SERVER', 'minio:9000')
    MINIO_ACCESS_KEY = os.environ.get('MINIO_ACCESS_KEY', '')
    MINIO_SECRET_KEY = os.environ.get('MINIO_SECRET_KEY', '')
    MINIO_BUCKET = os.environ.get('MINIO_BUCKET', 'entityservice')

    DATABASE_SERVER = os.environ.get('DATABASE_SERVER', 'db')
    DATABASE = os.environ.get('DATABASE', 'postgres')
    DATABASE_USER = os.environ.get('DATABASE_USER', 'postgres')
    DATABASE_PASSWORD = os.environ.get('DATABASE_PASSWORD', '')

    BROKER_URL = os.environ.get('CELERY_BROKER_URL',
                                'redis://:{}@{}:6379/0'.format(REDIS_PASSWORD, REDIS_SERVER))

    CELERY_RESULT_BACKEND = BROKER_URL
    CELERY_ANNOTATIONS = {
        'async_worker.calculate_mapping': {'rate_limit': '1/s'}
    }
    CELERYD_PREFETCH_MULTIPLIER = int(os.environ.get('CELERYD_PREFETCH_MULTIPLIER', '2'))
    CELERYD_MAX_TASKS_PER_CHILD = int(os.environ.get('CELERYD_MAX_TASKS_PER_CHILD', '4'))

    ENCRYPTION_MIN_KEY_LENGTH = int(os.environ.get('ENCRYPTION_MIN_KEY_LENGTH', '512'))

    ENCRYPTION_CHUNK_SIZE = int(os.environ.get('ENCRYPTION_CHUNK_SIZE', '100'))

    # Matches that have more than this number of possible comparisons will use the
    # faster greedy solver
    GREEDY_SIZE = int(os.environ.get('GREEDY_SIZE', '1000000'))

    # Number of comparisons to match per chunk. Default is a max size of 200M.
    # And a minimum size of 20M. Note larger jobs will favor larger chunks.
    MAX_GREEDY_CHUNK_SIZE = int(os.environ.get('MAX_CHUNK_SIZE', '200000000'))
    MIN_GREEDY_CHUNK_SIZE = int(os.environ.get('MIN_CHUNK_SIZE', '20000000'))

    # Anything above this threshold is considered a match. Note each mapping job can override this
    ENTITY_MATCH_THRESHOLD = float(os.environ.get('ENTITY_MATCH_THRESHOLD', '0.95'))

    ENTITY_CACHE_THRESHOLD = int(os.environ.get('ENTITY_CACHE_THRESHOLD', '1000000'))

    RAW_FILENAME_FMT = "quarantine/{}.txt"
    BIN_FILENAME_FMT = "raw-clks/{}.bin"

