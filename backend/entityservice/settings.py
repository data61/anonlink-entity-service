"""
Config shared between the application backend and the celery workers.
"""
import datetime
import os


class Config(object):
    """
    Hard coded default configuration which can be overwritten with environment variables.
    """

    # If adding or deleting any, please ensure that the changelog will mention them.
    CONNEXION_STRICT_VALIDATION = os.getenv("CONNEXION_STRICT_VALIDATION", "true").lower() == "true"
    CONNEXION_RESPONSE_VALIDATION = os.getenv("CONNEXION_RESPONSE_VALIDATION", "true").lower() == "true"

    LOG_CONFIG_FILENAME = os.getenv("LOG_CFG")
    TRACING_CONFIG_FILENAME = os.getenv("TRACE_CFG")

    LOGFILE = os.getenv("LOGFILE")
    LOG_HTTP_HEADER_FIELDS = os.getenv("LOG_HTTP_HEADER_FIELDS")

    REDIS_SERVER = os.getenv('REDIS_SERVER', 'redis')
    REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', '')
    REDIS_USE_SENTINEL = os.getenv('REDIS_USE_SENTINEL', 'false').lower() == "true"
    REDIS_SENTINEL_NAME = os.getenv('REDIS_SENTINEL_NAME', 'mymaster')

    MINIO_SERVER = os.getenv('MINIO_SERVER', 'minio:9000')
    MINIO_ACCESS_KEY = os.getenv('MINIO_ACCESS_KEY', '')
    MINIO_SECRET_KEY = os.getenv('MINIO_SECRET_KEY', '')
    MINIO_BUCKET = os.getenv('MINIO_BUCKET', 'entityservice')

    UPLOAD_OBJECT_STORE_ENABLED = os.getenv('UPLOAD_OBJECT_STORE_ENABLED', 'true').lower() == "true"
    UPLOAD_OBJECT_STORE_STS_DURATION = int(os.getenv('UPLOAD_OBJECT_STORE_STS_DURATION', '43200'))
    UPLOAD_OBJECT_STORE_SERVER = os.getenv('UPLOAD_OBJECT_STORE_SERVER', MINIO_SERVER)
    UPLOAD_OBJECT_STORE_SECURE = os.getenv('UPLOAD_OBJECT_STORE_SECURE', 'true') == 'true'
    UPLOAD_OBJECT_STORE_ACCESS_KEY = os.getenv('UPLOAD_OBJECT_STORE_ACCESS_KEY', '')
    UPLOAD_OBJECT_STORE_SECRET_KEY = os.getenv('UPLOAD_OBJECT_STORE_SECRET_KEY', '')
    UPLOAD_OBJECT_STORE_BUCKET = os.getenv('UPLOAD_OBJECT_STORE_BUCKET', 'anonlink-uploads')

    DOWNLOAD_OBJECT_STORE_SERVER = os.getenv('DOWNLOAD_OBJECT_STORE_SERVER', MINIO_SERVER)
    DOWNLOAD_OBJECT_STORE_SECURE = os.getenv('DOWNLOAD_OBJECT_STORE_SECURE', 'true') == 'true'
    DOWNLOAD_OBJECT_STORE_ACCESS_KEY = os.getenv('DOWNLOAD_OBJECT_STORE_ACCESS_KEY', '')
    DOWNLOAD_OBJECT_STORE_SECRET_KEY = os.getenv('DOWNLOAD_OBJECT_STORE_SECRET_KEY', '')
    DOWNLOAD_OBJECT_STORE_STS_DURATION = int(os.getenv('DOWNLOAD_OBJECT_STORE_STS_DURATION', '43200'))

    DATABASE_SERVER = os.getenv('DATABASE_SERVER', 'db')
    DATABASE = os.getenv('DATABASE', 'postgres')
    DATABASE_USER = os.getenv('DATABASE_USER', 'postgres')
    DATABASE_PASSWORD = os.getenv('DATABASE_PASSWORD', '')

    FLASK_DB_MIN_CONNECTIONS = os.getenv('FLASK_DB_MIN_CONNECTIONS', '1')
    FLASK_DB_MAX_CONNECTIONS = os.getenv('FLASK_DB_MAX_CONNECTIONS', '10')

    CELERY_BROKER_URL = os.getenv(
        'CELERY_BROKER_URL',
        ('sentinel://:{}@{}:26379/0' if REDIS_USE_SENTINEL else 'redis://:{}@{}:6379/0').format(REDIS_PASSWORD, REDIS_SERVER)
    )

    CELERY_DB_MIN_CONNECTIONS = os.getenv('CELERY_DB_MIN_CONNECTIONS', '1')
    CELERY_DB_MAX_CONNECTIONS = os.getenv('CELERY_DB_MAX_CONNECTIONS', '3')

    CELERY_BROKER_TRANSPORT_OPTIONS = {'master_name': "mymaster"} if REDIS_USE_SENTINEL else {}

    CELERY_RESULT_BACKEND = CELERY_BROKER_URL
    CELERY_RESULT_BACKEND_TRANSPORT_OPTIONS = {'master_name': "mymaster"} if REDIS_USE_SENTINEL else {}

    CELERY_ANNOTATIONS = {
        # Note that these are per worker instance per task rate limits.
        # tasks would get delayed before being run
        # https://celery.readthedocs.io/en/latest/userguide/tasks.html#Task.rate_limit
        #'entityservice.tasks.comparing.create_comparison_jobs': {'rate_limit': '1/m'}
    }

    CELERY_ROUTES = {
        'entityservice.tasks.comparing.create_comparison_jobs': {'queue': 'celery'},
        'entityservice.tasks.comparing.compute_filter_similarity': {'queue': 'compute'},
        'entityservice.tasks.comparing.aggregate_comparisons': {'queue': 'highmemory'},
        'entityservice.tasks.solver.solver_task': {'queue': 'highmemory'},
        'entityservice.tasks.permutation.save_and_permute': {'queue': 'highmemory'},
        'entityservice.tasks.encoding_uploading.handle_raw_upload': {'queue': 'celery'}
    }

    CELERYD_PREFETCH_MULTIPLIER = int(os.getenv('CELERYD_PREFETCH_MULTIPLIER', '1'))
    CELERYD_MAX_TASKS_PER_CHILD = int(os.getenv('CELERYD_MAX_TASKS_PER_CHILD', '2048'))
    # number of concurrent worker processes/threads, executing tasks
    CELERYD_CONCURRENCY = int(os.getenv("CELERYD_CONCURRENCY", '2'))
    CELERY_ACKS_LATE = os.getenv('CELERY_ACKS_LATE', 'false') == 'true'

    # Number of comparisons per chunk (on average).
    CHUNK_SIZE_AIM = int(os.getenv('CHUNK_SIZE_AIM', '300_000_000'))

    # If there are more than 1M CLKS, don't cache them in redis
    MAX_CACHE_SIZE = int(os.getenv('MAX_CACHE_SIZE', '1000000'))

    # Global limits on maximum number of candidate pairs considered.
    # If a run exceeds these limits, the run is put into an error state and further processing
    # is abandoned to protect the service from running out of memory.
    SOLVER_MAX_CANDIDATE_PAIRS = int(os.getenv('SOLVER_MAX_CANDIDATE_PAIRS', '100_000_000'))
    SIMILARITY_SCORES_MAX_CANDIDATE_PAIRS = int(os.getenv('SIMILARITY_SCORES_MAX_CANDIDATE_PAIRS', '500_000_000'))

    _CACHE_EXPIRY_SECONDS = int(os.getenv('CACHE_EXPIRY_SECONDS', datetime.timedelta(days=10).total_seconds()))
    CACHE_EXPIRY = datetime.timedelta(seconds=_CACHE_EXPIRY_SECONDS)

    ENTITY_CACHE_THRESHOLD = int(os.getenv('ENTITY_CACHE_THRESHOLD', '1000000'))

    RAW_FILENAME_FMT = "quarantine/{}.txt"
    BIN_FILENAME_FMT = "raw-clks/{}.bin"
    SIMILARITY_SCORES_FILENAME_FMT = "similarity-scores/{}.bin"

    # Encoding size (in bytes)
    MIN_ENCODING_SIZE = int(os.getenv('MIN_ENCODING_SIZE', '1'))
    MAX_ENCODING_SIZE = int(os.getenv('MAX_ENCODING_SIZE', '1024'))
