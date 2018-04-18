from entityservice.database.util import query_db
from entityservice.database.selections import get_dataprovider_id


def check_project_auth(db, resource_id, results_token):
    return query_db(db, """
        select count(*) from projects
        WHERE
          project_id = %s AND
          access_token = %s
        """, [resource_id, results_token], one=True)['count'] == 1


def check_update_auth(db, update_token):
    return get_dataprovider_id(db, update_token) is not None