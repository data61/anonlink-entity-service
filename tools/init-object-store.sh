#!/bin/sh
mc --version
echo "== Initialising Object Store =="
export MC_HOST_minio=http://$MINIO_ACCESS_KEY:$MINIO_SECRET_KEY@$MINIO_SERVER
mc mb minio/$UPLOAD_BUCKET
mc admin user add minio $UPLOAD_ONLY_ACCESS_KEY $UPLOAD_ONLY_SECRET_ACCESS_KEY
mc admin policy set minio writeonly user=$UPLOAD_ONLY_ACCESS_KEY
echo "== Object Store Initialised =="
