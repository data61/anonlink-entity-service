#!/bin/sh
mc --version
echo "== Initialising Object Store =="
if [ "$OBJECT_STORE_SECURE" = "true" ] || [ "$OBJECT_STORE_SECURE" = "True" ]
then
  OBJECT_STORE_SCHEME="https"
else
  OBJECT_STORE_SCHEME="http"
fi
export MC_HOST_minio="$OBJECT_STORE_SCHEME://$MINIO_ACCESS_KEY:$MINIO_SECRET_KEY@$MINIO_SERVER"
mc mb minio/$UPLOAD_OBJECT_STORE_BUCKET
mc admin user add minio $UPLOAD_OBJECT_STORE_ACCESS_KEY $UPLOAD_OBJECT_STORE_SECRET_KEY
mc admin policy set minio writeonly user=$UPLOAD_OBJECT_STORE_ACCESS_KEY
echo "== Object Store Root Upload User Created =="
mc admin user add minio $DOWNLOAD_OBJECT_STORE_ACCESS_KEY $DOWNLOAD_OBJECT_STORE_SECRET_KEY
mc admin policy set minio readonly user=$DOWNLOAD_OBJECT_STORE_ACCESS_KEY
echo "== Object Store Root Download User Created =="
echo "== Object Store Initialised =="
