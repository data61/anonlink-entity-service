import os
from datetime import datetime, timedelta

from celery import Celery, Task
from celery.utils.log import get_task_logger
import psycopg2.extras

from serialization import deserialize_filters
from database import *
from settings import Config as config

import anonlink

celery = Celery('tasks', broker=config.BROKER_URL, backend=config.CELERY_RESULT_BACKEND)
celery.conf.CELERY_TASK_SERIALIZER = 'json'
celery.conf.CELERY_ACCEPT_CONTENT = ['json']
celery.conf.CELERYBEAT_SCHEDULE = {
    'check-every-few-minutes': {
        'task': 'async_worker.frequent_task',
        'schedule': timedelta(seconds=120),
        'args': ()
    },
}

logger = get_task_logger(__name__)
logger.info("Setting up celery...")


@celery.task()
def frequent_task():
    """This task runs in a celery worker and is triggered by the beat scheduler
    according celery configuration.
    """
    logger.info("Carrying out the frequent task...")


@celery.task(ignore_result=True)
def calculate_mapping(resource_id):
    logger.info("Checking we need to calculating mapping")
    logger.debug(resource_id)

    db = connect_db()
    is_already_calculated, mapping_db_id = check_mapping_ready(db, resource_id)
    if is_already_calculated:
        logger.info("Mapping '{}' is already computed. Skipping".format(resource_id))
        return
    logger.info("Calculating mapping ")
    # Get the data provider IDS
    dp_ids = list(map(lambda d: d['id'], query_db(db, """
        SELECT id
        FROM dataproviders
        WHERE
          mapping = %s AND uploaded = TRUE
        """, [mapping_db_id])))

    logger.info("Data providers: {}".format(dp_ids))
    assert len(dp_ids) == 2, "Only support two party comparisons at the moment"

    logger.debug("Deserializing filters")
    filters1 = deserialize_filters(get_filter(db, dp_ids[0]))
    filters2 = deserialize_filters(get_filter(db, dp_ids[1]))

    logger.debug("Computing similarity")
    similarity = anonlink.entitymatch.calculate_filter_similarity(filters1, filters2)
    logger.debug("Calculating optimal connections for entire network")
    mapping = anonlink.network_flow.map_entities(similarity, threshold=0.95, method='weighted')

    logger.info("Mapping calculated. Persisting to database.")
    with db.cursor() as cur:
        logger.debug("Saving the blooming data")
        cur.execute("""
            UPDATE mappings SET
            mapping = (%s), ready = TRUE
            """,
            [psycopg2.extras.Json(mapping)])

    db.commit()
    logger.info("Mapping saved")

    return 'Done'
