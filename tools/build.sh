#!/usr/bin/env bash
set -e
cd $(dirname "$0")
cd ..

export APPVERSION=$(cat backend/entityservice/VERSION)

docker build -t quay.io/n1analytics/entity-app:latest backend

# Build docs and make them available for entity-nginx
SRC_DIR=`pwd`
BUILD_DIR=`pwd`/frontend/static
docker build -t quay.io/n1analytics/linkage-doc-builder docs
docker run --rm -v ${SRC_DIR}:/src -v ${BUILD_DIR}:/build quay.io/n1analytics/linkage-doc-builder
docker build -t quay.io/n1analytics/entity-nginx:latest frontend
