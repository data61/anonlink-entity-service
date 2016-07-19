# N1 Entity Matching Microservice

[![Backend Docker Repository on Quay](https://quay.io/repository/n1analytics/entity-app/status?token=ec8444d6-f940-4dcf-a840-2a077f56fb1b "Backend Docker Repository on Quay")](https://quay.io/repository/n1analytics/entity-app)

[![Nginx Docker Repository on Quay](https://quay.io/repository/n1analytics/entity-nginx/status "Nginx Docker Repository on Quay")](https://quay.io/repository/n1analytics/entity-nginx)

[![Postgres Docker Repository on Quay](https://quay.io/repository/n1analytics/entity-db-server/status?token=35be0156-f6a5-4916-96a3-849aee10c6b2 "Postgres Docker Repository on Quay")](https://quay.io/repository/n1analytics/entity-db-server)

### Dependencies

[Docker](http://docs.docker.com/installation/) and [docker-compose](http://docs.docker.com/compose/)

## Build

Provided you have quay.io credentials you can skip this step and docker will pull the
latest images when you start the service.

Run `./tools/build.sh` (from this directory, not from `tools`). This will create the tagged
images used by `docker-compose`.

## Start

Everything can be started at once with:

    docker-compose -f tools/docker-compose.yml up

This will start the following containers:

- nginx frontend
- gunicorn/flask backend
- celery backend worker
- postgres database
- redis job queue

The service should be running on port `8851`.

# Testing

A simple query with curl should tell you the status of the service:

    curl localhost:8851/api/v1/status
    {
        "number_mappings": 0,
        "status": "ok"
    }

With docker you should be able to use the same container to test the service:

    docker run -it \
        -e ENTITY_SERVICE_URL=http://<ENTITY-SERVER-HOST>:8851/api/v1 \
        -e ENTITY_SERVICE_TEST_SIZE=1000 \
        -e ENTITY_SERVICE_TEST_REPEATS=1 \
        --net=host \
        quay.io/n1analytics/entity-app python test_service.py

Alternatively set the environment variable `ENTITY_SERVICE_TIMING_TEST` to
anything, and the test_service will carry out a benchmark.

Note the `--net` parameter is only required if connecting to a service running locally
with docker compose. If the network is not recognized, use `docker network ls` to
see the available docker networks and find which network was created by docker-compose.

The `<ENTITY-SERVER-HOST>` is either the hostname or the host's IP address on the
docker network. When running locally with docker compose, **do not use `0.0.0.0`**,
there are two solutions:

- find the name of the `entity-nginx` container with `docker ps` (in the column `names`)
- use the local IP of the container with
  `docker inspect --format='{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' <container-id>`

Then use the previous command with `-e ENTITY_SERVICE_URL=http://<container-ip-or-name>:8851/api/v1`

# Data generation

    docker run -it \
        -v <place-to-put-generated-data>:/var/www/data \
        -e ENTITY_SERVICE_TEST_SIZE=10000 \
        quay.io/n1analytics/entity-app python generate_test_data.py

Note: the folder in which the generated data will be stored need to be existing.

## Development Tips

You might need to destroy the docker volumes used to store the postgres database if
you change the database schema:

    docker-compose -f tools/docker-compose.yml rm --all


During development you can run the redis and database containers with
docker-compose, and directly run the celery and flask applications with Python.


    docker-compose -f tools/docker-compose.yml run es_db

    docker-compose -f tools/docker-compose.yml run es_redis

## Scaling

You can run additional worker containers by scaling with docker-compose:

    docker-compose -f tools/docker-compose.yml scale es_worker=2


# Name generation

    http://<SERVER>:8851/danger/generate-names?n=10&p=0.5

Where n is the number of entities you want and p is the overlap proportion.
