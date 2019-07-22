#!/usr/bin/env bash
set -e
cd $(dirname "$0")
cd ..

export APPVERSION=$(cat backend/entityservice/VERSION)

docker build -t data61/anonlink-app:latest backend
docker build -t data61/anonlink-benchmark:latest benchmarking

# Build docs and make them available for anonlink-nginx
SRC_DIR=`pwd`
BUILD_DIR=`pwd`/frontend/static
docker build -t data61/anonlink-docs-tutorials docs/tutorial
docker build -t data61/anonlink-nginx:latest frontend
