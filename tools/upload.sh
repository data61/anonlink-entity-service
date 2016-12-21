#!/usr/bin/env bash

echo "Pushing images to quay.io"
docker push quay.io/n1analytics/entity-app:v1.2.1
docker push quay.io/n1analytics/entity-nginx:v1.2
docker push quay.io/n1analytics/entity-db-server:v1
echo "Success"
