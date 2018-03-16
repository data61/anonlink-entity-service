#!/usr/bin/env python3.4
"""
Config shared between the application backend and the celery workers.
"""
import os
import math
import logging


class Config(object):
    """
    Hard coded default configuration which can be overwritten with environment variables
    """

    DEBUG = os.environ.get("DEBUG", "false") == "true"

    LOGFILE = os.environ.get("LOGFILE", 'entity-service.log')
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
    CELERY_ROUTES = {
        'async_worker.calculate_mapping': {'queue': 'celery'},
        'async_worker.compute_similarity': {'queue': 'compute'},
        'async_worker.save_and_permute': {'queue': 'celery'},
        'async_worker.handle_raw_upload': {'queue': 'celery'}
    }

    CELERYD_PREFETCH_MULTIPLIER = int(os.environ.get('CELERYD_PREFETCH_MULTIPLIER', '1'))
    CELERYD_MAX_TASKS_PER_CHILD = int(os.environ.get('CELERYD_MAX_TASKS_PER_CHILD', '4'))
    CELERY_ACKS_LATE = os.environ.get('CELERY_ACKS_LATE', 'false') == 'true'

    ENCRYPTION_MIN_KEY_LENGTH = int(os.environ.get('ENCRYPTION_MIN_KEY_LENGTH', '512'))

    ENCRYPTION_CHUNK_SIZE = int(os.environ.get('ENCRYPTION_CHUNK_SIZE', '100'))

    # Matches that have more than this number of possible comparisons will use the
    # faster greedy solver
    GREEDY_SIZE = int(os.environ.get('GREEDY_SIZE', '1000000'))

    # Number of comparisons per chunk. Default is to interpolate between the min
    # of 100M and the max size of 1B based on the JOB_SIZE parameters.
    SMALL_COMPARISON_CHUNK_SIZE = int(os.environ.get('SMALL_COMPARISON_CHUNK_SIZE', '100000000'))
    LARGE_COMPARISON_CHUNK_SIZE = int(os.environ.get('LARGE_COMPARISON_CHUNK_SIZE', '1000000000'))

    # Anything smaller that this will use SMALL_COMPARISON_CHUNK_SIZE
    SMALL_JOB_SIZE = int(os.environ.get('SMALL_JOB_SIZE', '100000000'))
    # Anything greater than this will use LARGE_COMPARISON_CHUNK_SIZE
    LARGE_JOB_SIZE = int(os.environ.get('LARGE_JOB_SIZE', '100000000000'))

    # If there are more than 1M CLKS, don't cache them in redis
    MAX_CACHE_SIZE = int(os.environ.get('MAX_CACHE_SIZE', '1000000'))

    MIN_GREEDY_CHUNK_SIZE = int(os.environ.get('MIN_CHUNK_SIZE', '20000000'))

    # Anything above this threshold is considered a match. Note each mapping job can override this
    ENTITY_MATCH_THRESHOLD = float(os.environ.get('ENTITY_MATCH_THRESHOLD', '0.95'))

    ENTITY_CACHE_THRESHOLD = int(os.environ.get('ENTITY_CACHE_THRESHOLD', '1000000'))

    RAW_FILENAME_FMT = "quarantine/{}.txt"
    BIN_FILENAME_FMT = "raw-clks/{}.bin"
    SIMILARITY_SCORES_FILENAME_FMT = "similarity-scores/{}.csv"

    @classmethod
    def get_task_chunk_size(cls, size):
        if size <= cls.SMALL_JOB_SIZE:
            return None
        elif size >= cls.LARGE_JOB_SIZE:
            chunk_size = cls.LARGE_COMPARISON_CHUNK_SIZE
        else:
            # Interpolate
            gradient = (cls.LARGE_COMPARISON_CHUNK_SIZE - cls.SMALL_COMPARISON_CHUNK_SIZE) / (cls.LARGE_JOB_SIZE - cls.SMALL_JOB_SIZE)
            chunk_size = cls.SMALL_COMPARISON_CHUNK_SIZE + size * gradient

        return math.ceil(math.sqrt(chunk_size))
