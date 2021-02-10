#!/usr/bin/env bash
set -e
cd $(dirname "$0")
cd ..

export APPVERSION=$(cat backend/entityservice/VERSION)

#docker build -t data61/anonlink-base:latest base

docker build -t data61/anonlink-app:latest backend
docker build -t data61/anonlink-benchmark:latest benchmarking

# Build docs and make them available for anonlink-nginx
docker build -t data61/anonlink-docs-tutorials docs/tutorial
docker build -t data61/anonlink-nginx:latest -f frontend/Dockerfile .
