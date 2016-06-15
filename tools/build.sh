#!/usr/bin/env bash
cd backend
docker pull python:3.5
docker build --no-cache -t quay.io/n1analytics/entity-app .
cd ../frontend
docker build -t quay.io/n1analytics/entity-nginx .
cd ..
