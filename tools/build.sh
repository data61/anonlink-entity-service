#!/usr/bin/env bash
set -e
cd $(dirname "$0")

git submodule init
git submodule update

cd ..
export APPVERSION=$(cat backend/VERSION)
export BRANCH_NAME=$(git rev-parse --abbrev-ref HEAD)


if [ "$BRANCH_NAME" = "master" ];
then
    docker build -t quay.io/n1analytics/entity-app:$APPVERSION backend
    docker build -t quay.io/n1analytics/entity-nginx:v1.2.6 frontend
else
    docker build -t quay.io/n1analytics/entity-app:$BRANCH_NAME backend
    docker build -t quay.io/n1analytics/entity-nginx:$BRANCH_NAME frontend
fi
