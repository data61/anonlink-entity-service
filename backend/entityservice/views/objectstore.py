import json

import opentracing
from flask import request
from minio.credentials import AssumeRoleProvider, Credentials
from structlog import get_logger

from entityservice.settings import Config as config
import entityservice.database as db
from entityservice.object_store import connect_to_upload_object_store, connect_to_object_store, create_bucket, \
    object_store_download_only_client
from entityservice.utils import safe_fail_request, object_store_upload_path
from entityservice.views import bind_log_and_span, precheck_upload_token
from entityservice.views.serialization import ObjectStoreCredentials


def _get_upload_policy(bucket_name="uploads", path="*"):

    restricted_upload_policy = {
      "Version": "2012-10-17",
      "Statement": [
        {
          "Action": [
            "s3:PutObject"
          ],
          "Effect": "Allow",
          "Resource": [
            "arn:aws:s3:::{}/{}".format(bucket_name, path),
            "arn:aws:s3:::{}/{}/*".format(bucket_name, path),
          ],
          "Sid": "Upload-access-to-specific-bucket-only"
        }
      ]
    }

    return json.dumps(restricted_upload_policy)


def _get_download_policy(bucket_name, path):

    policy = {
      "Version": "2012-10-17",
      "Statement": [
        {
          "Action": [
            "s3:GetObject"
          ],
          "Effect": "Allow",
          "Resource": [
            "arn:aws:s3:::{}/{}".format(bucket_name, path),
            "arn:aws:s3:::{}/{}/*".format(bucket_name, path),
          ],
          "Sid": "download-specific-path-only"
        }
      ]
    }

    return json.dumps(policy)


def authorize_external_upload(project_id):
    if not config.UPLOAD_OBJECT_STORE_ENABLED:
        safe_fail_request(500,
                          message="Retrieving temporary object store credentials feature disabled",
                          title="Feature Disabled")

    headers = request.headers

    log, parent_span = bind_log_and_span(project_id)

    log.debug("Authorizing external upload")
    token = precheck_upload_token(project_id, headers, parent_span)
    log.debug(f"Update token is valid")
    with db.DBConn() as conn:
        dp_id = db.get_dataprovider_id(conn, token)
        log = log.bind(dpid=dp_id)

    with opentracing.tracer.start_span('assume-role-request', child_of=parent_span):
        client = connect_to_upload_object_store()
        client.set_app_info("anonlink", "development version")

        bucket_name = config.UPLOAD_OBJECT_STORE_BUCKET
        path = object_store_upload_path(project_id, dp_id)
        log.info(f"Retrieving temporary object store credentials for path: '{bucket_name}/{path}'")
        scheme = "https" if config.UPLOAD_OBJECT_STORE_SECURE else "http"
        credentials_provider = AssumeRoleProvider(
            f'{scheme}://{config.UPLOAD_OBJECT_STORE_SERVER}/',
            access_key=config.UPLOAD_OBJECT_STORE_ACCESS_KEY,
            secret_key=config.UPLOAD_OBJECT_STORE_SECRET_KEY,
            policy=_get_upload_policy(bucket_name, path=path),
            duration_seconds=config.UPLOAD_OBJECT_STORE_STS_DURATION
        )
        credential_values = credentials_provider.retrieve()

        expiry = credential_values._expiration

        log.info("Retrieved temporary credentials")

        client = connect_to_object_store()
        if not client.bucket_exists(bucket_name):
            log.warning(f'bucket "{bucket_name}" does not exist! Trying to create now...')
            create_bucket(client, bucket_name)

    credentials_json = ObjectStoreCredentials().dump(credential_values)
    log.debug("Temp credentials", **credentials_json)

    # Convert datetime to ISO 8601 string
    credentials_json["Expiration"] = expiry.strftime('%Y-%m-%dT%H:%M:%S.%f%z')

    return {
        "credentials": credentials_json,
        "upload": {
            "endpoint": config.UPLOAD_OBJECT_STORE_SERVER,
            "secure": config.UPLOAD_OBJECT_STORE_SECURE,
            "bucket": bucket_name,
            "path": path
        }
    }, 201


def prepare_restricted_download_response(bucket_name, path):
    """
    Creates temporary object store credentials that allow pulling objects
    from the given path for a set amount of time.

    Note this doesn't copy data from one object store to another.
    """
    log = get_logger()
    client = object_store_download_only_client()
    client.set_app_info("anonlink", "development version")

    log.info(f"Retrieving temporary object store credentials for path: '{bucket_name}/{path}'")
    scheme = "https" if config.DOWNLOAD_OBJECT_STORE_SECURE else "http"
    credentials_provider = AssumeRoleProvider(
        f"{scheme}://{config.DOWNLOAD_OBJECT_STORE_SERVER}/",
        access_key=config.DOWNLOAD_OBJECT_STORE_ACCESS_KEY,
        secret_key=config.DOWNLOAD_OBJECT_STORE_SECRET_KEY,
        policy=_get_download_policy(bucket_name, path=path),
        duration_seconds=config.DOWNLOAD_OBJECT_STORE_STS_DURATION
    )
    credential_values = credentials_provider.retrieve()
    expiry = credential_values._expiration

    log.info("Retrieved temporary credentials")

    credentials_json = ObjectStoreCredentials().dump(credential_values)

    # Convert datetime to ISO 8601 string
    credentials_json["Expiration"] = expiry.strftime('%Y-%m-%dT%H:%M:%S.%f%z')

    return {
        "credentials": credentials_json,
        "object": {
            # Note this may be different from the internal minio endpoint
            "endpoint": config.DOWNLOAD_OBJECT_STORE_SERVER,
            "secure": config.DOWNLOAD_OBJECT_STORE_SECURE,
            "bucket": bucket_name,
            "path": path
        }
    }, 200
