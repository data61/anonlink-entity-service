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
    logger.debug("checking authorization token to update data")
    with DBConn() as conn:
        resource_exists = db.check_update_auth(conn, update_token)
    if not resource_exists:
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
    # check if the following combinations are true
    # - uses_blocking is False AND 'clks' element in upload JSON
    # - uses_blocking if True AND 'clknblocks' element in upload JSON
    # otherwise, return safe_fail_request
    is_valid_clks = not uses_blocking and 'clks' in clk_json
    is_valid_clknblocks = uses_blocking and 'clknblocks' in clk_json
    if not (is_valid_clks or is_valid_clknblocks):
        # fail condition1 - uses_blocking is True but uploaded element is "clks"
        if uses_blocking and 'clks' in clk_json:
            safe_fail_request(400, message='Uploaded element is "clks" while expecting "clknblocks"')
        # fail condition2 - uses_blocking is False but uploaded element is "clknblocks"
        if not uses_blocking and 'clknblocks' in clk_json:
            safe_fail_request(400, message='Uploaded element is "clknblocks" while expecting "clks"')
        # fail condition3 - "clks" exist in JSON but there is no data
        if 'clks' in clk_json and len(clk_json['clks']) < 1:
            safe_fail_request(400, message='Missing CLKs information')
        # fail condition4 - "clknblocks" exist in JSON but there is no data
        if 'clknblocks' in clk_json and len(clk_json['clknblocks']) < 1:
            safe_fail_request(400, message='Missing CLK and Blocks information')
        # fail condition5 - unknown element in JSON
        if 'clks' not in clk_json and 'clknblocks' not in clk_json:
            safe_fail_request(400, message='Unknown upload element - expect "clks" or "clknblocks"')


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
