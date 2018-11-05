import logging

from celery import Celery
from celery.signals import task_prerun, task_postrun
import structlog

from entityservice.settings import Config as config


celery = Celery('tasks',
                broker=config.BROKER_URL,
                backend=config.CELERY_RESULT_BACKEND
                )

celery.conf.CELERY_TASK_SERIALIZER = 'json'
celery.conf.CELERY_ACCEPT_CONTENT = ['json']
celery.conf.CELERY_RESULT_SERIALIZER = 'json'
celery.conf.CELERY_ANNOTATIONS = config.CELERY_ANNOTATIONS
celery.conf.CELERYD_PREFETCH_MULTIPLIER = config.CELERYD_PREFETCH_MULTIPLIER
celery.conf.CELERYD_MAX_TASKS_PER_CHILD = config.CELERYD_MAX_TASKS_PER_CHILD
celery.conf.CELERY_ACKS_LATE = config.CELERY_ACKS_LATE
celery.conf.CELERY_ROUTES = config.CELERY_ROUTES


structlog.configure(
    processors=[
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.dev.ConsoleRenderer()
    ],
    context_class=structlog.threadlocal.wrap_dict(dict),
    logger_factory=structlog.stdlib.LoggerFactory(),
)

logger = structlog.wrap_logger(logging.getLogger('celery.es'))
if config.DEBUG:
    logging.getLogger('celery').setLevel(logging.INFO)
    logging.getLogger('celery.es').setLevel(logging.DEBUG)

logger.info("Setting up celery worker")
logger.debug("Debug logging enabled")


@task_prerun.connect()
def configure_structlog(sender, body=None, **kwargs):
    task = kwargs['task']
    task.logger = logger.new(
        task_id=kwargs['task_id'],
        task_name=sender.__name__
    )

