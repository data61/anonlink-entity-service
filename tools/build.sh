#!/usr/bin/env bash
set -e
cd $(dirname "$0")
cd ..

export APPVERSION=$(cat backend/VERSION)

docker build -t quay.io/n1analytics/entity-app:latest backend
docker build -t quay.io/n1analytics/entity-nginx:latest frontend
#docker build -t quay.io/n1analytics/entity-app:doc-builder docs
