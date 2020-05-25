import platform

import anonlink
import psycopg2.errors

from entityservice.cache import service_status
import entityservice.database as db
from entityservice.utils import safe_fail_request
from entityservice.version import __version__


def status_get():
    """Displays the latest mapping statistics"""

    status = service_status.get_status()

    if status is None:
        # We ensure we can connect to the database during the status check
        with db.DBConn() as conn:
            try:
                number_of_mappings = db.query_db(conn, '''
                            SELECT COUNT(*) FROM projects
                            ''', one=True)['count']
            except psycopg2.errors.UndefinedTable:
                safe_fail_request(500, "DB uninitialized")

            current_rate = db.get_latest_rate(conn)

        status = {
            'status': 'ok',
            'project_count': number_of_mappings,
            'rate': current_rate
        }

        service_status.set_status(status)
    return status


def version_get():
    return {
        'anonlink': anonlink.__version__,
        'entityservice': __version__,
        'python': platform.python_version()
    }
