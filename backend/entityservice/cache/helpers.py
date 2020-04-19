def _get_run_hash_key(run_id):
    key = f'run:{run_id}'
    return key


def _get_project_hash_key(project_id):
    key = f'project:{project_id}'
    return key


def _convert_redis_result_to_int(res):
    # redis returns bytes, and None if not present
    if res is not None:
        return int(res)
    else:
        return None