from typing import List

import minio
from minio.credentials import Credentials
from minio.deleteobjects import DeleteObject
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


def object_store_download_only_client():
    """
    Instantiate a minio client with a get only policy applied.

    :return:
    """
    mc = minio.Minio(
        config.MINIO_SERVER,
        config.DOWNLOAD_OBJECT_STORE_ACCESS_KEY,
        config.DOWNLOAD_OBJECT_STORE_SECRET_KEY,
        region="us-east-1",
        secure=False
    )
    mc.set_app_info("anonlink-upload", "minio client for downloads")
    logger.debug("Connected to minio download account")
    return mc


def create_bucket(minio_client, bucket):
    if not minio_client.bucket_exists(bucket):
        logger.info("Creating bucket {}".format(bucket))
        try:
            minio_client.make_bucket(bucket)
        except minio.S3Error:
            logger.info("The bucket {} was not created.".format(bucket))


def stat_and_stream_object(bucket_name, object_name):
    mc = connect_to_object_store()
    logger.debug("Checking object exists in object store")
    stat = mc.stat_object(bucket_name=bucket_name, object_name=object_name)
    logger.debug("Retrieving file from object store")
    response = mc.get_object(bucket_name=bucket_name, object_name=object_name)
    return stat, response


def parse_minio_credentials(credentials):
    if credentials:
        access_key = credentials['AccessKeyId']
        secret_key = credentials['SecretAccessKey']
        session_token = credentials.get('SessionToken', None)
        mc_credentials = Credentials(access_key=access_key, secret_key=secret_key, session_token=session_token)
    else:
        mc_credentials = None
    return mc_credentials


def delete_object_store_folder(mc, bucket_name, path):
    objects_to_delete = mc.list_objects(bucket_name, prefix=path, recursive=True)
    objects_to_delete = [DeleteObject(x.object_name) for x in objects_to_delete]
    for del_err in mc.remove_objects(bucket_name, objects_to_delete):
        logger.warning("Deletion Error: {}".format(del_err))


def delete_object_store_files(mc, object_infos: List):
    """ An object info is a dict which contains entries for 'path' and 'bucket'"""
    for object_info in object_infos:
        path = object_info.get('path')
        bucket = object_info.get('bucket')
        try:
            mc.remove_object(bucket, path)
            logger.info(f"Deleted file {bucket}/{path} after db ingestion.")
        except Exception as e:
            logger.warning(f"Could not delete file {path} in bucket {bucket} on object store: {e}")
