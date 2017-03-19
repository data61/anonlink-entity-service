#!/usr/bin/env bash
docker save --output=n1-entity-app.tar.gz quay.io/n1analytics/entity-app:v1.4.9
docker save --output=n1-entity-nginx.tar.gz  quay.io/n1analytics/entity-nginx:v1.2.7
docker save --output=n1-entity-db.tar.gz postgres:9.5
