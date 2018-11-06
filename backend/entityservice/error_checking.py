from entityservice.database import DBConn, get_project_schema_encoding_size, get_filter_metadata, \
    update_encoding_metadata
from entityservice.settings import Config as config
from entityservice.tasks import delete_minio_objects


class InvalidEncodingError(ValueError):
    pass


def check_dataproviders_encoding(project_id, encoding_size):
    """
    Ensure that the provided encoding size is valid for the given project.

    :raises ValueError if encoding_size invalid.
    """
    with DBConn() as db:
        project_encoding_size = get_project_schema_encoding_size(db, project_id)
    if project_encoding_size is not None and encoding_size != project_encoding_size:
        raise InvalidEncodingError("User provided encodings were invalid size")

    if not config.MIN_ENCODING_SIZE <= encoding_size <= config.MAX_ENCODING_SIZE:
        raise InvalidEncodingError("Encoding size out of bounds")


def handle_invalid_encoding_data(project_id, dp_id):
    with DBConn() as conn:
        filename = get_filter_metadata(conn, dp_id)
        update_encoding_metadata(conn, 'DELETED', dp_id, state='error')
    delete_minio_objects.delay([filename], project_id)
