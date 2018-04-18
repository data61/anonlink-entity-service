import platform

import anonlink
from flask_restful import Resource

from entityservice import cache
import entityservice.database as db
from entityservice.database import get_db
from entityservice.version import __version__
from entityservice.messages import INVALID_ACCESS_MSG

from entityservice import app
from entityservice.utils import safe_fail_request


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
            'libc': "".join(platform.libc_ver()),
            'python': platform.python_version()
        }


def abort_if_project_doesnt_exist(resource_id):
    resource_exists = db.check_project_exists(get_db(), resource_id)
    if not resource_exists:
        app.logger.info("Requested project resource with invalid identifier token")
        safe_fail_request(403, message=INVALID_ACCESS_MSG)


def abort_if_invalid_dataprovider_token(update_token):
    app.logger.debug("checking authorization token to update data")
    resource_exists = db.check_update_auth(get_db(), update_token)
    if not resource_exists:
        safe_fail_request(403, message=INVALID_ACCESS_MSG)


def is_results_token_valid(resource_id, results_token):
    if not db.check_project_auth(get_db(), resource_id, results_token):
        return False
    else:
        return True


def is_receipt_token_valid(resource_id, receipt_token):
    if db.select_dataprovider_id(get_db(), resource_id, receipt_token) is None:
        return False
    else:
        return True


def abort_if_invalid_results_token(resource_id, results_token):
    app.logger.debug("checking authorization token to fetch results data")
    if not is_results_token_valid(resource_id, results_token):
        app.logger.debug("Auth invalid")
        safe_fail_request(403, message=INVALID_ACCESS_MSG)


def dataprovider_id_if_authorize(resource_id, receipt_token):
    app.logger.debug("checking authorization token to fetch mask data")
    if not is_receipt_token_valid(resource_id, receipt_token):
        safe_fail_request(403, message=INVALID_ACCESS_MSG)

    dp_id = db.select_dataprovider_id(get_db(), resource_id, receipt_token)
    return dp_id


def node_id_if_authorize(resource_id, token):
    """
    In case of a permutation with an unencrypted mask, we are using both the result token and the
    receipt tokens. The result token is used by the coordinator to get the mask. The receipts tokens
    are used by the dataproviders to get their permutations. However, we do not know before checking
    which is the type of the received token.
    """
    app.logger.debug("checking authorization token to fetch results data")
    # If the token is not a valid result token, it should be a receipt token.
    if not is_results_token_valid(resource_id, token):
        app.logger.debug("checking authorization token to fetch permutation data")
        # If the token is not a valid receipt token, we abort.
        if not is_receipt_token_valid(resource_id, token):
            safe_fail_request(403, message=INVALID_ACCESS_MSG)
        dp_id = db.select_dataprovider_id(get_db(), resource_id, token)
    else:
        dp_id = "Coordinator"
    return dp_id