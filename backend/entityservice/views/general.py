import platform

import anonlink
from flask_restful import Resource

from entityservice import cache
import entityservice.database as db
from entityservice.version import __version__


class Status(Resource):

    def get(self):
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


class Version(Resource):

    def get(self):
        return {
            'anonlink': anonlink.__version__,
            'entityservice': __version__,
            'python': platform.python_version()
        }


