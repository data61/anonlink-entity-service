"""
Testing:
 - uploading over existing files
 - using deleted credentials
 - using expired credentials

"""
import io

import minio
from minio import Minio
import pytest
from minio.credentials import AssumeRoleProvider, Credentials

from entityservice.object_store import connect_to_object_store, connect_to_upload_object_store
from entityservice.settings import Config

restricted_upload_policy = """{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Action": [
        "s3:PutObject"
      ],
      "Effect": "Allow",
      "Resource": [
        "arn:aws:s3:::uploads/2020/*"
      ],
      "Sid": "Upload-access-to-specific-bucket-only"
    }
  ]
} 
"""


class TestAssumeRole:

    def test_temp_credentials_minio(self):

        upload_endpoint = Config.UPLOAD_OBJECT_STORE_SERVER
        bucket_name = "uploads"

        root_mc_client = connect_to_object_store()
        upload_restricted_minio_client = connect_to_upload_object_store()
        if not root_mc_client.bucket_exists(bucket_name):
            root_mc_client.make_bucket(bucket_name)

        with pytest.raises(minio.error.AccessDenied):
            upload_restricted_minio_client.list_buckets()

        # Should be able to put an object though
        upload_restricted_minio_client.put_object(bucket_name, 'testobject', io.BytesIO(b'data'), length=4)

        credentials_provider = AssumeRoleProvider(upload_restricted_minio_client,
                                                  Policy=restricted_upload_policy
                                                  )
        temp_creds = Credentials(provider=credentials_provider)

        newly_restricted_mc_client = Minio(upload_endpoint, credentials=temp_creds, region='us-east-1', secure=False)

        with pytest.raises(minio.error.AccessDenied):
            newly_restricted_mc_client.list_buckets()

        # Note this put object worked with the earlier credentials
        # But should fail if we have applied the more restrictive policy
        with pytest.raises(minio.error.AccessDenied):
            newly_restricted_mc_client.put_object(bucket_name, 'testobject2', io.BytesIO(b'data'), length=4)

        # this path is allowed in the policy however
        newly_restricted_mc_client.put_object(bucket_name, '2020/testobject', io.BytesIO(b'data'), length=4)
