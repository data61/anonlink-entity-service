import logging

from celery import Celery
from celery import signals
import structlog

from entityservice.database.util import init_db_pool, close_db_pool
from entityservice.settings import Config
from entityservice.logger_setup import setup_structlog

celery = Celery('tasks',
                broker=Config.CELERY_BROKER_URL,
                backend=Config.CELERY_RESULT_BACKEND
                )

celery.conf.task_annotations = Config.CELERY_ANNOTATIONS
celery.conf.task_acks_late = Config.CELERY_ACKS_LATE
celery.conf.task_routes = Config.CELERY_ROUTES
celery.conf.broker_transport_options = Config.CELERY_BROKER_TRANSPORT_OPTIONS
celery.conf.result_backend_transport_options = Config.CELERY_RESULT_BACKEND_TRANSPORT_OPTIONS
celery.conf.worker_prefetch_multiplier = Config.CELERYD_PREFETCH_MULTIPLIER
celery.conf.worker_max_tasks_per_child = Config.CELERYD_MAX_TASKS_PER_CHILD

if Config.CELERYD_CONCURRENCY > 0:
    # If set to 0, let celery choose the default, which is the number of available CPUs on the machine.
    celery.conf.worker_concurrency = Config.CELERYD_CONCURRENCY


# Set up our logging
setup_structlog()
logger = structlog.wrap_logger(logging.getLogger('entityservice.tasks'))


@signals.worker_process_init.connect()
def init_worker(**kwargs):
    db_min_connections = Config.CELERY_DB_MIN_CONNECTIONS
    db_max_connections = Config.CELERY_DB_MAX_CONNECTIONS
    init_db_pool(db_min_connections, db_max_connections)
    logger.info("Setting up worker process")
    logger.debug("Debug logging enabled")


@signals.worker_process_shutdown.connect()
def shutdown_worker(**kwargs):
    close_db_pool()
    logger.info("Shutting down a worker process")



@signals.task_prerun.connect()
def configure_structlog(sender, body=None, **kwargs):
    task = kwargs['task']
    task.logger = logger.new(
        task_name=sender.__name__
    )
