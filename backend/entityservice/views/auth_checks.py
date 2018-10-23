from entityservice import database as db
from entityservice.database import get_db, get_project_column
from entityservice.messages import INVALID_ACCESS_MSG
from entityservice.utils import safe_fail_request
from structlog import get_logger

logger = get_logger()


def abort_if_project_doesnt_exist(project_id):
    resource_exists = db.check_project_exists(get_db(), project_id)
    if not resource_exists:
        logger.info("Requested project resource with invalid identifier token")
        safe_fail_request(403, message=INVALID_ACCESS_MSG)


def abort_if_run_doesnt_exist(project_id, run_id):
    resource_exists = db.check_run_exists(get_db(), project_id, run_id)
    if not resource_exists:
        logger.info("Requested project or run resource with invalid identifier token")
        safe_fail_request(403, message=INVALID_ACCESS_MSG)


def abort_if_invalid_dataprovider_token(update_token):
    logger.debug("checking authorization token to update data")
    resource_exists = db.check_update_auth(get_db(), update_token)
    if not resource_exists:
        safe_fail_request(403, message=INVALID_ACCESS_MSG)


def is_results_token_valid(project_id, results_token):
    return db.check_project_auth(get_db(), project_id, results_token)


def is_receipt_token_valid(resource_id, receipt_token):
    return db.select_dataprovider_id(get_db(), resource_id, receipt_token) is not None


def abort_if_invalid_results_token(resource_id, results_token):
    logger.debug("checking authorization of 'result_token'")
    if not is_results_token_valid(resource_id, results_token):
        logger.debug("Authorization denied")
        safe_fail_request(403, message=INVALID_ACCESS_MSG)


def dataprovider_id_if_authorize(resource_id, receipt_token):
    logger.debug("checking authorization token to fetch mask data")
    if not is_receipt_token_valid(resource_id, receipt_token):
        safe_fail_request(403, message=INVALID_ACCESS_MSG)

    dp_id = db.select_dataprovider_id(get_db(), resource_id, receipt_token)
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
    result_type = get_project_column(get_db(), project_id, 'result_type')
    if result_type in {'mapping', 'similarity_scores'} and token_type == 'receipt_token':
        logger.info("Caller provided receipt token to get results")
        safe_fail_request(403, message=INVALID_ACCESS_MSG)
    return token_type
