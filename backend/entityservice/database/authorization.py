from entityservice.database.util import query_db
from entityservice.database.selections import get_dataprovider_id


def check_project_auth(db, project_id, results_token):
    sql_query = """
        select count(*) from projects
        WHERE
          project_id = %s AND
          access_token = %s
        """

    query_result = query_db(db, sql_query, [project_id, results_token], one=True)
    return query_result['count'] == 1


def check_update_auth(db, update_token):
    return get_dataprovider_id(db, update_token) is not None
