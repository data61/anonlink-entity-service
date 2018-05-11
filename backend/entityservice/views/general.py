import platform

import anonlink

from entityservice import cache
import entityservice.database as db
from entityservice.version import __version__


def status_get():
    """Displays the latest mapping statistics"""

    status = cache.get_status()

    if status is None:
        # We ensure we can connect to the database during the status check
        db1 = db.get_db()

        number_of_mappings = db.query_db(db1, '''
                    SELECT COUNT(*) FROM projects
                    ''', one=True)['count']

        current_rate = db.get_latest_rate(db1)

        status = {
            'status': 'ok',
            'project_count': number_of_mappings,
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
