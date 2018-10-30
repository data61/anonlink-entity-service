from entityservice.database import DBConn, get_project_schema_encoding_size
from entityservice.settings import Config as config


def check_dataproviders_encoding(project_id, encoding_size):
    """
    Ensure that the provided encoding size is valid for the given project.

    :raises ValueError if encoding_size invalid.
    """
    with DBConn() as db:
        project_encoding_size = get_project_schema_encoding_size(db, project_id)
    if project_encoding_size is not None and encoding_size != project_encoding_size:
        raise ValueError("User provided encodings were invalid size")

    if not config.MIN_ENCODING_SIZE <= encoding_size <= config.MAX_ENCODING_SIZE:
        raise ValueError("Encoding size out of bounds")

