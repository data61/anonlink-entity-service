#!/usr/bin/env bash
docker save --output=n1-entity-app.tar.gz quay.io/n1analytics/entity-app:v1
docker save --output=n1-entity-nginx.tar.gz  quay.io/n1analytics/entity-nginx:v1
docker save --output=n1-entity-db.tar.gz  quay.io/n1analytics/entity-db-server:v1
