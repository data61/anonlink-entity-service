import io

import minio
import pytest

from e2etests.config import url
from e2etests.util import generate_overlapping_clk_data


class TestAuthorizeExternalUpload:

    def test_get_auth_credentials(self, requests, a_project):
        expected_number_parties = 2
        datasets = generate_overlapping_clk_data(
            [100] * expected_number_parties, overlap=0.8)

        for dp_index in range(expected_number_parties):
            pid = a_project['project_id']
            res = requests.get(url + f"projects/{pid}/authorize-external-upload",
                               headers={'Authorization': a_project['update_tokens'][dp_index]})

            assert res.status_code == 201
            raw_json = res.json()
            assert "credentials" in raw_json
            credentials = raw_json['credentials']
            assert "upload" in raw_json

            minio_endpoint = raw_json['upload']['endpoint']
            minio_secure = raw_json['upload']['secure']
            bucket_name = raw_json['upload']['bucket']
            allowed_path = raw_json['upload']['path']

            for key in ['AccessKeyId', 'SecretAccessKey', 'SessionToken', 'Expiration']:
                assert key in credentials

            # Test we can create and use these credentials via a Minio client
            restricted_mc_client = minio.Minio(
                minio_endpoint,
                credentials['AccessKeyId'],
                credentials['SecretAccessKey'],
                credentials['SessionToken'],
                region='us-east-1',
                secure=minio_secure
            )

            # Client shouldn't be able to list buckets
            with pytest.raises(minio.error.AccessDenied):
                restricted_mc_client.list_buckets()

            with pytest.raises(minio.error.AccessDenied):
                restricted_mc_client.put_object(bucket_name, 'testobject', io.BytesIO(b'data'), length=4)

            # Should be able to put an object in the approved path
            restricted_mc_client.put_object(bucket_name, allowed_path + '/blocks.json', io.BytesIO(b'data'), length=4)
            # Permission exists to upload multiple files in the approved path
            restricted_mc_client.put_object(bucket_name, allowed_path + '/encodings.bin', io.BytesIO(b'data'), length=4)

            # Client shouldn't be allowed to download files
            with pytest.raises(minio.error.AccessDenied):
                restricted_mc_client.get_object(bucket_name, allowed_path + '/blocks.json')

            # Client shouldn't be allowed to delete uploaded files:
            with pytest.raises(minio.error.AccessDenied):
                restricted_mc_client.remove_object(bucket_name, allowed_path + '/blocks.json')

            # Client shouldn't be able to list objects in the bucket
            with pytest.raises(minio.error.AccessDenied):
                list(restricted_mc_client.list_objects(bucket_name))

            # client shouldn't be able to list objects even in the approved path
            with pytest.raises(minio.error.AccessDenied):
                list(restricted_mc_client.list_objects(bucket_name, prefix=allowed_path))

            # Should be able to notify the service that we've uploaded data
            res = requests.post(url + f"projects/{pid}/clks",
                                headers={'Authorization': a_project['update_tokens'][dp_index]},
                                json={
                                    'encodings': datasets[dp_index]
                                }
                               )
            assert res.status_code == 201
