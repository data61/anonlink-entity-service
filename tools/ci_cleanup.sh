#!/usr/bin/env bash

sleep 5
cd deploy/entity-service
docker-compose -f tools/docker-compose.yml -f tools/ci.yml -p entityservicetest down
