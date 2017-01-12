#!/usr/bin/env bash
set -e
script_name=$(basename "$0")
cd $(dirname "$0")

if [ "$BRANCH_NAME" = "master" ];
then
    echo "Pushing images to quay.io";
    export APPVERSION=$(cat ../backend/VERSION);
    docker push quay.io/n1analytics/entity-app:$APPVERSION;
    docker push quay.io/n1analytics/entity-nginx:v1.2.3;
    docker push quay.io/n1analytics/entity-db-server:v1;
else
    echo "Skipping upload as not in master branch";
fi
