import minio
from structlog import get_logger

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
