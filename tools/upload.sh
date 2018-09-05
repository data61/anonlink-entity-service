#!/usr/bin/env bash
set -e
script_name=$(basename "$0")
cd $(dirname "$0")

if [ -z ${BRANCH_NAME+x} ]; then
    export BRANCH_NAME=$(git rev-parse --abbrev-ref HEAD)
else
    echo "BRANCH_NAME is set to '$BRANCH_NAME'";
fi

export ENTITY_APP_LABEL=$(python get_docker_tag.py $BRANCH_NAME app)
export ENTITY_NGINX_LABEL=$(python get_docker_tag.py $BRANCH_NAME nginx)
export ENTITY_BENCHMARK_LABEL=$(python get_docker_tag.py $BRANCH_NAME benchmark)

echo "Tagging images: $ENTITY_APP_LABEL and $ENTITY_NGINX_LABEL and $ENTITY_BENCHMARK_LABEL";

docker tag quay.io/n1analytics/entity-app:latest quay.io/n1analytics/entity-app:${ENTITY_APP_LABEL};
docker tag quay.io/n1analytics/entity-nginx:latest quay.io/n1analytics/entity-nginx:${ENTITY_NGINX_LABEL};
docker tag quay.io/n1analytics/entity-benchmark:latest quay.io/n1analytics/entity-benchmark:${ENTITY_BENCHMARK_LABEL};
docker tag quay.io/n1analytics/entity-docs:latest quay.io/n1analytics/entity-docs:${ENTITY_APP_LABEL};

echo "Pushing images to quay.io";
docker push quay.io/n1analytics/entity-app:${ENTITY_APP_LABEL};
docker push quay.io/n1analytics/entity-docs:${ENTITY_APP_LABEL};
docker push quay.io/n1analytics/entity-nginx:${ENTITY_NGINX_LABEL};
docker push quay.io/n1analytics/entity-benchmark:${ENTITY_BENCHMARK_LABEL};

echo "Images uploaded";
