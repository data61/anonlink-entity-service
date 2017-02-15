#!/usr/bin/env bash
set -e
cd $(dirname "$0")

git submodule init
git submodule update

cd ../backend
export APPVERSION=$(cat VERSION)
docker build -t quay.io/n1analytics/entity-app:$APPVERSION .
cd ../frontend
docker build -t quay.io/n1analytics/entity-nginx:v1.2.6 .
cd ../db-server
docker build -t quay.io/n1analytics/entity-db-server:v1.1 .
cd ..
