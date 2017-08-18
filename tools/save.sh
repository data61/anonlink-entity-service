#!/usr/bin/env bash

set -e
cd $(dirname "$0")
cd ..

export APPVERSION=$(cat backend/VERSION)


docker save --output=n1-entity-app.tar.gz quay.io/n1analytics/entity-app:$APPVERSION
docker save --output=n1-entity-nginx.tar.gz  quay.io/n1analytics/entity-nginx:v1.3.0
docker save --output=n1-entity-db.tar.gz postgres:9.6
