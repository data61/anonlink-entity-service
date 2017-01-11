#!/usr/bin/env bash

export COMPOSE_PROJECT_NAME=entityservicetest

# Stop and remove any existing entity service
docker-compose -f tools/docker-compose.yml -f tools/ci.yml -p entityservicetest down -v

# Build the images
./tools/build.sh

# Start all the containers
docker-compose -f tools/docker-compose.yml -f tools/ci.yml -p entityservicetest up -d

sleep 5
docker ps

# Follow the logs of the testing container
docker logs -t -f entityservicetest_ci_1

# Raise the exit code of the tests
exit `docker inspect --format='{{.State.ExitCode}}' entityservicetest_ci_1`
