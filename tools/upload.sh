#!/usr/bin/env bash
set -e
echo "Pushing images to quay.io"
export APPVERSION=$(cat VERSION)
docker push quay.io/n1analytics/entity-app:$APPVERSION
docker push quay.io/n1analytics/entity-nginx:v1.2
docker push quay.io/n1analytics/entity-db-server:v1
echo "Success"
