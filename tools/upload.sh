#!/usr/bin/env bash

echo "Tagging images for quay.io"
docker tag n1analytics/entity-app quay.io/n1analytics/entity-app
docker tag n1analytics/entity-nginx quay.io/n1analytics/entity-nginx

echo "Pushing images to quay.io"
docker push quay.io/n1analytics/entity-app
docker push quay.io/n1analytics/entity-nginx

echo "Success"
