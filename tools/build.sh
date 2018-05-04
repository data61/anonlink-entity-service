#!/usr/bin/env bash
set -e
cd $(dirname "$0")
cd ..

export APPVERSION=$(cat backend/entityservice/VERSION)

docker build -t quay.io/n1analytics/entity-app:latest backend

# Build docs and make them available for entity-nginx
SRC_DIR=`pwd`/docs
BUILD_DIR=`pwd`/frontend/static
docker build -t quay.io/n1analytics/entity-app:doc-builder docs
docker run -it -v ${SRC_DIR}:/src -v ${BUILD_DIR}:/build quay.io/n1analytics/entity-app:doc-builder

docker build -t quay.io/n1analytics/entity-nginx:latest frontend
