import minio
from structlog import get_logger

from entityservice.database import logger, insert_similarity_score_file
from entityservice.errors import RunDeleted

from entityservice.settings import Config as config

logger = get_logger('objectstore')


def connect_to_object_store():
    mc = minio.Minio(
        config.MINIO_SERVER,
        config.MINIO_ACCESS_KEY,
        config.MINIO_SECRET_KEY,
        secure=False
    )
    logger.debug("Connected to minio")
    if not mc.bucket_exists(config.MINIO_BUCKET):
        logger.info("Creating bucket {}".format(config.MINIO_BUCKET))
        mc.make_bucket(config.MINIO_BUCKET)
    return mc


def store_similarity_scores(buffer, run_id, length, conn):
    """
    Stores the similarity scores above a similarity threshold as a CSV in minio.

    :param buffer: a stream of csv bytes where each row contains similarity_scores:
                                - the index of an entity from dataprovider 1
                                - the index of an entity from dataprovider 1
                                - the similarity score between 0 and 1 of the best match
    :param run_id:
    :param length:
    """
    log = logger.bind(run_id=run_id)
    filename = config.SIMILARITY_SCORES_FILENAME_FMT.format(run_id)

    log.info("Storing similarity score results in CSV file: {}".format(filename))
    mc = connect_to_object_store()
    mc.put_object(
        config.MINIO_BUCKET,
        filename,
        data=buffer,
        length=length,
        content_type='application/csv'
    )

    try:
        log.debug("Storing the CSV filename '{}' in the database".format(filename))
        result_id = insert_similarity_score_file(conn, run_id, filename)
        log.debug("Saved path to similarity scores file to db with id {}".format(result_id))
    except psycopg2.IntegrityError:
        log.info("Error saving similarity score filename to database. Suspect that project has been deleted")
        raise RunDeleted(run_id)
    return filename