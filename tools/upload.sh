#!/usr/bin/env bash
set -e
script_name=$(basename "$0")
cd $(dirname "$0")

export APPVERSION=$(cat ../backend/VERSION)

if [ -z ${BRANCH_NAME+x} ]; then
    export BRANCH_NAME=$(git rev-parse --abbrev-ref HEAD)
else
    echo "BRANCH_NAME is set to '$BRANCH_NAME'";
fi

if [ "$BRANCH_NAME" = "master" ];
then
    echo "Pushing images to quay.io";
    docker push quay.io/n1analytics/entity-app:${APPVERSION};
    docker push quay.io/n1analytics/entity-nginx:v1.3.0;
else
    echo "Uploading with label: ${BRANCH_NAME}";

    docker tag quay.io/n1analytics/entity-app:${APPVERSION} quay.io/n1analytics/entity-app:${BRANCH_NAME};
    docker tag quay.io/n1analytics/entity-nginx:v1.3.0 quay.io/n1analytics/entity-nginx:${BRANCH_NAME};

    docker push quay.io/n1analytics/entity-app:${BRANCH_NAME};
    docker push quay.io/n1analytics/entity-nginx:${BRANCH_NAME};
fi
