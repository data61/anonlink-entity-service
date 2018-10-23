import minio
from structlog import get_logger

from entityservice.settings import Config

logger = get_logger('objectstore')


def connect_to_object_store():
    mc = minio.Minio(
        Config.MINIO_SERVER,
        Config.MINIO_ACCESS_KEY,
        Config.MINIO_SECRET_KEY,
        secure=False
    )
    logger.debug("Connected to minio")
    if not mc.bucket_exists(Config.MINIO_BUCKET):
        logger.info("Creating bucket {}".format(Config.MINIO_BUCKET))
        mc.make_bucket(Config.MINIO_BUCKET)
    return mc
