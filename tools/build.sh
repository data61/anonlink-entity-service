#!/usr/bin/env bash
cd backend
docker pull python:3.5
docker build -t quay.io/n1analytics/entity-app:v1 .
cd ../frontend
docker build -t quay.io/n1analytics/entity-nginx:v1 .
cd ../db-server
docker build -t quay.io/n1analytics/entity-db-server:v1 .
cd ..
