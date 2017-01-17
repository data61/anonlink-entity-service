#!/usr/bin/env bash

set -e
cd $(dirname "$0")

export COMPOSE_PROJECT_NAME=entityservicetest

# Stop and remove any existing entity service
docker-compose -f docker-compose.yml -f ci.yml -p entityservicetest down -v

# Build the images
./build.sh

# Start all the containers including tests
docker-compose -f docker-compose.yml -f ci.yml -p entityservicetest up -d

sleep 5

# Follow the logs of the testing container
docker logs -t -f entityservicetest_ci_1

echo "Other Logs:"

docker logs entityservicetest_es_backend_1
docker logs entityservicetest_es_nginx_1

echo "Cleanup:"
./ci_cleanup.sh

# Raise the exit code of the tests
exit `docker inspect --format='{{.State.ExitCode}}' entityservicetest_ci_1`
