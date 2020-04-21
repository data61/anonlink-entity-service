import os
from time import sleep

import minio
import pytest

from entityservice.settings import Config as config

@pytest.fixture(scope='session')
def upload_restricted_minio_client():

    sleep(int(os.getenv('INITIAL_DELAY', '5')))

    restricted_mc_client = minio.Minio(
        config.UPLOAD_OBJECT_STORE_SERVER,
        config.UPLOAD_OBJECT_STORE_ACCESS_KEY,
        config.UPLOAD_OBJECT_STORE_SECRET_KEY,
        region='us-east-1',
        secure=False
    )
    restricted_mc_client.set_app_info("anonlink-restricted", "testing client")
    return restricted_mc_client
