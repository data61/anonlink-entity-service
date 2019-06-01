import logging

from celery import Celery
from celery.signals import task_prerun
import structlog

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


# Set up our logging
setup_structlog()
logger = structlog.wrap_logger(logging.getLogger('entityservice.tasks'))
logger.info("Setting up entityservice worker")
logger.debug("Debug logging enabled")


@task_prerun.connect()
def configure_structlog(sender, body=None, **kwargs):
    task = kwargs['task']
    task.logger = logger.new(
        task_id=kwargs['task_id'],
        task_name=sender.__name__
    )
