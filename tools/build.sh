#!/usr/bin/env bash
set -e
cd $(dirname "$0")

git submodule init
git submodule update

cd ..
export APPVERSION=$(cat backend/VERSION)


docker build -t quay.io/n1analytics/entity-app:$APPVERSION backend
docker build -t quay.io/n1analytics/entity-nginx:v1.2.7 frontend
