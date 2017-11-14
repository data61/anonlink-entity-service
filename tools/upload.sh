#!/usr/bin/env bash
set -e
script_name=$(basename "$0")
cd $(dirname "$0")

export APPVERSION=$(cat ../backend/VERSION)
export NGINXVERSION=$(cat ../frontend/VERSION)

if [ -z ${BRANCH_NAME+x} ]; then
    export BRANCH_NAME=$(git rev-parse --abbrev-ref HEAD)
else
    echo "BRANCH_NAME is set to '$BRANCH_NAME'";
fi

if [ "$BRANCH_NAME" = "master" ];
then
    export ENTITY_APP_LABEL="$APPVERSION";
    export ENTITY_NGINX_LABEL="$NGINXVERSION";
else
    export ENTITY_APP_LABEL="$APPVERSION-$BRANCH_NAME";
    export ENTITY_NGINX_LABEL="$NGINXVERSION-$BRANCH_NAME";
fi

echo "Tagging images: $ENTITY_APP_LABEL and $ENTITY_NGINX_LABEL";

docker tag quay.io/n1analytics/entity-app:latest quay.io/n1analytics/entity-app:${ENTITY_APP_LABEL};
docker tag quay.io/n1analytics/entity-nginx:latest quay.io/n1analytics/entity-nginx:${ENTITY_NGINX_LABEL};

echo "Pushing images to quay.io";
docker push quay.io/n1analytics/entity-app:${ENTITY_APP_LABEL};
docker push quay.io/n1analytics/entity-nginx:${ENTITY_NGINX_LABEL};
