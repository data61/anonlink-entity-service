import platform

from structlog import get_logger

import anonlink

from entityservice import cache
import entityservice.database as db
from entityservice.metrics import STATUS_REQUEST_COUNT, STATUS_REQUEST_LATENCY, COMPARISON_RATE_GAUGE, PROJECT_COUNT
from entityservice.version import __version__


logger = get_logger()


@STATUS_REQUEST_LATENCY.time()
def status_get():
    """Displays the latest mapping statistics"""

    status = cache.get_status()
    STATUS_REQUEST_COUNT.inc()

    if status is None:
        # We ensure we can connect to the database during the status check
        with db.DBConn() as conn:
            number_of_projects = db.query_db(conn, '''
                        SELECT COUNT(*) FROM projects
                        ''', one=True)['count']

            current_rate = db.get_latest_rate(conn)

            COMPARISON_RATE_GAUGE.set(current_rate)
            PROJECT_COUNT.set(number_of_projects)

        status = {
            'status': 'ok',
            'project_count': number_of_projects,
            'rate': current_rate
        }

        cache.set_status(status)
    return status


def version_get():
    return {
        'anonlink': anonlink.__version__,
        'entityservice': __version__,
        'python': platform.python_version()
    }
