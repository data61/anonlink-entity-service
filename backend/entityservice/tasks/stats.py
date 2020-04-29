from datetime import timedelta

from entityservice.async_worker import celery, logger
from entityservice.database import DBConn, get_elapsed_run_times
from entityservice.database import get_total_comparisons_for_project
from entityservice.database import insert_comparison_rate


@celery.task(ignore_result=True)
def calculate_comparison_rate():
    with DBConn() as dbinstance:
        logger.info("Calculating global comparison rate")

        total_comparisons = 0
        total_time = timedelta(0)
        for run in get_elapsed_run_times(dbinstance):

            comparisons = get_total_comparisons_for_project(dbinstance, run['project_id'])

            if comparisons != 'NA':
                total_comparisons += comparisons
            else:
                logger.debug("Skipping run as it hasn't completed")
            total_time += run['elapsed']

        if total_time.total_seconds() > 0:
            rate = total_comparisons/total_time.total_seconds()
            logger.info("Total comparisons: {}".format(total_comparisons))
            logger.info("Total time:        {}".format(total_time.total_seconds()))
            logger.info("Comparison rate:   {:.0f}".format(rate))

            with dbinstance.cursor() as cur:
                insert_comparison_rate(cur, rate)

        else:
            logger.warning("Can't compute comparison rate yet")
