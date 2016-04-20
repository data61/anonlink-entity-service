# N1 Entity Matching Microservice

### Dependencies

[Docker](http://docs.docker.com/installation/) and [docker-compose](http://docs.docker.com/compose/)

## Build

Provided you have quay.io credentials you can skip this step and docker will pull the
latest images when you start the service.

Run `./tools/build.sh` (from this directory, not from `tools`). This will create the tagged
images used by `docker-compose`.

## Start

First start the database by itself.

    docker-compose -f tools/docker-compose.yml run db

This gives it a chance to create the tables and import any existing data.

Then exit that (Ctrl-C) and run:

    docker-compose -f tools/docker-compose.yml up

This will start the following containers:

- nginx frontend
- gunicorn/flask backend
- celery backend worker
- postgres database
- redis job queue

The service should be running on port `8851`.

# Testing

With docker you should be able to use the same container to test the service:

    docker run -it \
        -e ENTITY_SERVICE_URL=http://<ENTITY-SERVER-IPADDRESS>:8851/api/v1 \
        -e ENTITY_SERVICE_TEST_SIZE=1000 \
        -e ENTITY_SERVICE_TEST_REPEATS=10 \
        --net=tools_db \
        quay.io/n1analytics/entity-app python test_service.py

Note the `--net` parameter is only required if connecting to a service running locally
with docker compose. In this instance the <ENTITY_SERVER_IPADDRESS> is usually the
host's IP address on the docker bridge network.

# Data generation

    docker run -it \
        -v place-to-put-generated-data:/var/www/data \
        -e ENTITY_SERVICE_TEST_SIZE=10000 \
        n1analytics/entity-app python generate_test_data.py



## Development Tips

You might need to destroy the docker volumes used to store the postgres database if
you change the database schema:

    docker-compose -f tools/docker-compose.yml rm
    rm -fr ./tools/dbdata

During development you can run just the database container with the following:


