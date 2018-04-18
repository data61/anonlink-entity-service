from datetime import timedelta

from entityservice.database.util import query_db, execute_returning_id, logger


def get_latest_rate(db):
    res = query_db(db, 'select ts, rate from metrics order by ts desc limit 1', one=True)
    if res is None:
        # Just to avoid annoying divide by zero errors return a low rate
        # if the true value is unknown
        current_rate = 1
    else:
        current_rate = res['rate']

    return current_rate


def get_run_time(db, resource_id):
    res = query_db(db, """
        SELECT (now() - time_started) as elapsed
        from runs
        WHERE run_id = %s""",
                   [resource_id], one=True)['elapsed']

    return timedelta(seconds=0) if res is None else res


def insert_comparison_rate(cur, rate):
    return execute_returning_id(cur, """
        INSERT INTO metrics
        (rate) VALUES (%s)
        RETURNING id;
        """, [rate])