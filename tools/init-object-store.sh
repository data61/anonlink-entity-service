echo "== Initialising Object Store =="
mc --version
sleep ${INITIAL_DELAY}
mc mb minio/uploads
mc admin user add minio $UPLOAD_ONLY_ACCESS_KEY $UPLOAD_ONLY_SECRET_ACCESS_KEY
mc admin policy set minio writeonly user=$UPLOAD_ONLY_ACCESS_KEY
echo "== Object Store Initialised =="
