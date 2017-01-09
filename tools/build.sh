#!/usr/bin/env bash
set -e
cd backend
export APPVERSION=$(cat VERSION)
docker build -t quay.io/n1analytics/entity-app:$APPVERSION .
cd ../frontend
docker build -t quay.io/n1analytics/entity-nginx:v1.2 .
cd ../db-server
docker build -t quay.io/n1analytics/entity-db-server:v1 .
cd ..
