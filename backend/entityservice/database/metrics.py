from datetime import timedelta

from entityservice.database.util import query_db, execute_returning_id, logger


def get_latest_rate(db):
    select_query = 'select ts, rate from metrics order by ts desc limit 1'
    res = query_db(db, select_query, one=True)
    if res is None:
        # Just to avoid annoying divide by zero errors return a low rate
        # if the true value is unknown
        current_rate = 1
    else:
        current_rate = res['rate']

    return current_rate


def get_run_time(db, resource_id):
    sql_query = """
        SELECT (now() - time_started) as elapsed
        from runs
        WHERE run_id = %s
        """
    res = query_db(db, sql_query, [resource_id], one=True)['elapsed']

    return timedelta(seconds=0) if res is None else res


def insert_comparison_rate(cur, rate):
    insertion_stmt = """
        INSERT INTO metrics
        (rate) VALUES (%s)
        RETURNING id;
        """
    return execute_returning_id(cur, insertion_stmt, [rate])