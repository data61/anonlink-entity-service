mc --version
echo "== Initialising Object Store =="
mc mb minio/uploads
mc admin user add minio $UPLOAD_ONLY_ACCESS_KEY $UPLOAD_ONLY_SECRET_ACCESS_KEY
mc admin policy set minio writeonly user=$UPLOAD_ONLY_ACCESS_KEY
echo "== Object Store Initialised =="
