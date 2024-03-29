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

docker tag data61/anonlink-app:latest data61/anonlink-app:${ENTITY_APP_LABEL};
docker tag data61/anonlink-nginx:latest data61/anonlink-nginx:${ENTITY_NGINX_LABEL};
docker tag data61/anonlink-benchmark:latest data61/anonlink-benchmark:${ENTITY_BENCHMARK_LABEL};
docker tag data61/anonlink-docs-builder:latest data61/anonlink-docs-builder:${ENTITY_APP_LABEL};

echo "Pushing images";
docker push data61/anonlink-app:${ENTITY_APP_LABEL};
docker push data61/anonlink-docs-builder:${ENTITY_APP_LABEL};
docker push data61/anonlink-nginx:${ENTITY_NGINX_LABEL};
docker push data61/anonlink-benchmark:${ENTITY_BENCHMARK_LABEL};

if [[ $BRANCH_NAME = "develop" ]]
then
    echo "Also pushing images with tag 'latest'"
    docker push data61/anonlink-app:latest
    docker push data61/anonlink-docs-builder:latest
    docker push data61/anonlink-nginx:latest
    docker push data61/anonlink-benchmark:latest
fi

echo "Images uploaded";
