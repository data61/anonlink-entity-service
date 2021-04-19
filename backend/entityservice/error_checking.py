from structlog import get_logger
from textwrap import dedent

from entityservice.database import DBConn, get_project_schema_encoding_size, get_filter_metadata, \
    update_encoding_metadata
from entityservice.settings import Config as config
from entityservice.tasks import delete_minio_objects

logger = get_logger()


class InvalidEncodingError(ValueError):
    pass


def check_dataproviders_encoding(project_id, encoding_size):
    """
    Ensure that the provided encoding size is valid for the given project.

    :raises ValueError if encoding_size invalid.
    """
    if not config.MIN_ENCODING_SIZE <= encoding_size <= config.MAX_ENCODING_SIZE:
        raise InvalidEncodingError(dedent(f"""Encoding size out of bounds.
        Expected encoding size to be between {config.MIN_ENCODING_SIZE} and {config.MAX_ENCODING_SIZE}
        """))
    with DBConn() as db:
        project_encoding_size = get_project_schema_encoding_size(db, project_id)
        logger.debug(f"Project encoding size is {project_encoding_size}")
    if project_encoding_size is not None and encoding_size != project_encoding_size:
        raise InvalidEncodingError(dedent(f"""User provided encodings were an invalid size
        Expected {project_encoding_size} but got {encoding_size}.
        """))


def handle_invalid_encoding_data(project_id, dp_id):
    with DBConn() as conn:
        filename, _ = get_filter_metadata(conn, dp_id)
        update_encoding_metadata(conn, 'DELETED', dp_id, state='error')
    if filename is not None:
        delete_minio_objects.delay([filename], project_id)
