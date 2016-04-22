#!/usr/bin/env bash

echo "Pushing images to quay.io"
docker push quay.io/n1analytics/entity-app:latest
docker push quay.io/n1analytics/entity-nginx:latest
echo "Success"
