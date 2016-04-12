#!/usr/bin/env bash
cd backend
docker build -t n1analytics/entity-app .
cd ../frontend
docker build -t n1analytics/entity-nginx .
