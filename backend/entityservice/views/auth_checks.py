from structlog import get_logger

from entityservice import database as db
from entityservice.database import get_project_column, DBConn
from entityservice.messages import INVALID_ACCESS_MSG
from entityservice.utils import safe_fail_request

logger = get_logger()


def abort_if_project_in_error_state(project_id):
    with DBConn() as conn:
        num_parties_with_error = db.get_encoding_error_count(conn, project_id)
    if num_parties_with_error > 0:
        safe_fail_request(500, message="Can't post run as project has errors")


def abort_if_project_doesnt_exist(project_id):
    with DBConn() as conn:
        resource_exists = db.check_project_exists(conn, project_id)
    if not resource_exists:
        logger.info("Requested project resource with invalid identifier token")
        safe_fail_request(403, message=INVALID_ACCESS_MSG)


def abort_if_run_doesnt_exist(project_id, run_id):
    with DBConn() as conn:
        resource_exists = db.check_run_exists(conn, project_id, run_id)
    if not resource_exists:
        logger.info("Requested project or run resource with invalid identifier token")
        safe_fail_request(403, message=INVALID_ACCESS_MSG)


def abort_if_invalid_dataprovider_token(update_token):
    logger.debug("checking authorization token to upload data")
    with DBConn() as conn:
        resource_exists = db.check_update_auth(conn, update_token)
    if not resource_exists:
        logger.debug("authorization token invalid")
        safe_fail_request(403, message=INVALID_ACCESS_MSG)


def is_results_token_valid(project_id, results_token):
    with DBConn() as conn:
        return db.check_project_auth(conn, project_id, results_token)


def is_receipt_token_valid(resource_id, receipt_token):
    with DBConn() as conn:
        if db.select_dataprovider_id(conn, resource_id, receipt_token) is None:
            return False
        else:
            return True


def abort_if_invalid_results_token(resource_id, results_token):
    logger.debug("checking authorization of 'result_token'")
    if not is_results_token_valid(resource_id, results_token):
        logger.debug("Authorization denied")
        safe_fail_request(403, message=INVALID_ACCESS_MSG)


def abort_if_inconsistent_upload(uses_blocking, clk_json):
    """Check if the uploaded data is consistent with requirements imposed at the project
     level.

     Specifically checks that one of these combinations is true:

     If the project uses_blocking:
     - `clknblocks` element in upload JSON, OR
     - `blocks` element in uploaded JSON

     If the project doesn't use blocking:
      - No `blocks` element or `clksnblocks` elment in uploaded JSON.

    Finally checks that encodings are uploaded somehow by either `clksnblocks` or
    `encodings` being present in the uploaded JSON.

    If these conditions are not met raise a ValueError exception.

    :param uses_blocking: Boolean that indicates if the project uses blocking
    :param clk_json: a dict of the JSON from the client.
    :raises ValueError:
    """
    if uses_blocking:
        if 'clknblocks' not in clk_json and 'blocks' not in clk_json:
            raise ValueError('Expecting blocking information. Either in "blocks" or "clksnblocks"')
    else:
        if 'clknblocks' in clk_json or 'blocks' in clk_json:
            _msg = 'Blocking has been disabled for this project, but received blocking information'
            raise ValueError(_msg)

    if 'clknblocks' not in clk_json and 'encodings' not in clk_json and 'clks' not in clk_json:
        raise ValueError('Missing encoding information')


def dataprovider_id_if_authorize(resource_id, receipt_token):
    logger.debug("checking authorization token to fetch mask data")
    if not is_receipt_token_valid(resource_id, receipt_token):
        safe_fail_request(403, message=INVALID_ACCESS_MSG)

    with DBConn() as conn:
        dp_id = db.select_dataprovider_id(conn, resource_id, receipt_token)
    return dp_id


def get_authorization_token_type_or_abort(project_id, token):
    """
    In case of a permutation with an unencrypted mask, we are using both the result token and the receipt tokens.
    The result token reveals the mask. The receipts tokens are used by the dataproviders to get their permutations.
    However, we do not know the type of token we have before checking.
    """
    logger.debug("checking if provided authorization is a results_token")
    # If the token is not a valid result token, it should be a receipt token.
    if not is_results_token_valid(project_id, token):
        logger.debug("checking if provided authorization is receipt_token")
        # If the token is not a valid receipt token, we abort.
        if not is_receipt_token_valid(project_id, token):
            safe_fail_request(403, message=INVALID_ACCESS_MSG)
        token_type = 'receipt_token'
    else:
        token_type = 'result_token'

    # Note that at this stage we have EITHER a receipt or result token, and depending on the result_type
    # that might mean the caller is not authorized.
    with DBConn() as conn:
        result_type = get_project_column(conn, project_id, 'result_type')
    if result_type in {'groups', 'similarity_scores'} and token_type == 'receipt_token':
        logger.info("Caller provided receipt token to get results")
        safe_fail_request(403, message=INVALID_ACCESS_MSG)
    return token_type
