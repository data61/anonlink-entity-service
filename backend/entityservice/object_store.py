import minio
from structlog import get_logger

from entityservice.settings import Config as config

logger = get_logger('objectstore')


def connect_to_object_store(credentials=None):
    mc = minio.Minio(
        config.MINIO_SERVER,
        config.MINIO_ACCESS_KEY,
        config.MINIO_SECRET_KEY,
        credentials=credentials,
        secure=False
    )
    logger.debug("Connected to minio")
    mc.set_app_info("anonlink-client", "minio general client")
    create_bucket(mc, config.MINIO_BUCKET)
    return mc


def connect_to_upload_object_store():
    """
    Instantiate a minio client with an upload only policy applied.

    :return:
    """
    mc = minio.Minio(
        config.UPLOAD_OBJECT_STORE_SERVER,
        config.UPLOAD_OBJECT_STORE_ACCESS_KEY,
        config.UPLOAD_OBJECT_STORE_SECRET_KEY,
        region="us-east-1",
        secure=config.UPLOAD_OBJECT_STORE_SECURE
    )
    mc.set_app_info("anonlink-upload", "minio client for uploads")
    logger.debug("Connected to minio upload account")

    return mc


def create_bucket(minio_client, bucket):
    if not minio_client.bucket_exists(bucket):
        logger.info("Creating bucket {}".format(bucket))
        try:
            minio_client.make_bucket(bucket)
        except minio.error.BucketAlreadyOwnedByYou:
            logger.info("The bucket {} was already created.".format(bucket))


def stat_and_stream_object(bucket_name, object_name, credentials=None):
    mc = connect_to_object_store(credentials)
    logger.debug("Checking object exists in object store")
    stat = mc.stat_object(bucket_name=bucket_name, object_name=object_name)
    logger.debug("Retrieving file from object store")
    response = mc.get_object(bucket_name=bucket_name, object_name=object_name)
    return stat, response
