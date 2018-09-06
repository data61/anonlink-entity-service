import celery

from entityservice.errors import DBResourceMissing
import psycopg2
from structlog import get_logger

logger = get_logger()


class BaseTask(celery.Task):
    """Abstract base class for all tasks in Entity Service"""

    abstract = True
    throws = (DBResourceMissing, psycopg2.IntegrityError)

    def __call__(self, *args, **kwargs):
        logger.info('TASK STARTING: {0.name}[{0.request.id}]'.format(self))
        return super(BaseTask, self).__call__(*args, **kwargs)


    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Log the exceptions to some central logging system at retry."""
        #todo captureException(exc)
        logger.warning("Task {} is retrying after a '{}' exception".format(
            task_id, exc.__class__.__name__))

        super(BaseTask, self).on_retry(exc, task_id, args, kwargs, einfo)

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Log the exceptions"""
        logger.info("An exception '{}' was raised in a task".format(exc.__class__.__name__))

        if isinstance(exc, (DBResourceMissing, psycopg2.IntegrityError)):
            logger.info("Task was running when a resource was deleted, or db was inconsistent. Ignoring")
            # Note it will still be logged by celery
            # http://docs.celeryproject.org/en/master/userguide/tasks.html#Task.throws

        else:
            logger.exception(f"Unexpected exception raised in task {task_id}", exc_info=einfo)
            super(BaseTask, self).on_failure(exc, task_id, args, kwargs, einfo)

