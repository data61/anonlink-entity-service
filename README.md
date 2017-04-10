# N1 Entity Matching Microservice

[![Backend Docker Repository on Quay](https://quay.io/repository/n1analytics/entity-app/status?token=ec8444d6-f940-4dcf-a840-2a077f56fb1b "Backend Docker Repository on Quay")](https://quay.io/repository/n1analytics/entity-app) [![Nginx Docker Repository on Quay](https://quay.io/repository/n1analytics/entity-nginx/status "Nginx Docker Repository on Quay")](https://quay.io/repository/n1analytics/entity-nginx)

Allows two organizations to carry out private record linkage - without
disclosing personally identifiable information.

- Deployed to https://es.data61.xyz
- Jupyter notebook with tutorial available at: https://jupyter.es.data61.xyz


### Dependencies

[Docker](http://docs.docker.com/installation/) and [docker-compose](http://docs.docker.com/compose/)

## Checking out the code

This repository uses [git submodules](https://git-scm.com/book/en/v2/Git-Tools-Submodules), so to clone
use `git clone --recursive git@github.com:n1analytics/entity-service.git` or you will have to run:

```
git submodule init
git submodule update
```

Note to update the submodule's repo, you can update to the latest master with:

```
git submodule foreach git pull origin master
```

## Build

Provided you have quay.io credentials you can skip this step and docker will pull the
latest images when you start the service.

Run `./tools/build.sh` (from this directory, not from `tools`). This will create the tagged
images used by `docker-compose`.

## Start

Everything can be started locally using docker-compose with:

    docker-compose -f tools/docker-compose.yml up

This will start the following containers:

- nginx frontend
- gunicorn/flask backend
- celery backend worker
- postgres database
- redis job queue
- minio object store

The api service should be running on host port `8851`.

# Testing

A simple query with curl should tell you the status of the service:

    curl localhost:8851/api/v1/status
    {
        "number_mappings": 2,
        "rate": 44051409,
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
docker network. When running locally with docker compose, **do not use `0.0.0.0`** as 
inside the test container `0.0.0.0` refers to that container; there are two solutions:

### Finding the containers IP

- find the name of the `entity-nginx` container with `docker ps` (in the column `names`)
- use the local IP of the container with
  `docker inspect --format='{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' <container-id>`

Then use the previous command with `-e ENTITY_SERVICE_URL=http://<container-ip-or-name>:8851/api/v1`

### Testing with docker-compose

An additional docker-compose config file can be found in `./tools/ci.yml`,
this can be added in to run along with the rest of the service:

    docker-compose -f tools/docker-compose.yml -f ci.yml -p entityservicetest up -d


# Data generation

    docker run -it \
        -v <place-to-put-generated-data>:/var/www/data \
        -e ENTITY_SERVICE_TEST_SIZE=10000 \
        quay.io/n1analytics/entity-app python generate_test_data.py

Note: the folder in which the generated data will be stored need to be existing.

## Development Tips

### Volumes

You might need to destroy the docker volumes used for the object store
and the postgres database:

    docker-compose -f tools/docker-compose.yml rm --all


### Mix and match docker compose

During development you can run the redis and database containers with
docker-compose, and directly run the celery and flask applications with Python.


    docker-compose -f tools/docker-compose.yml run es_db

    docker-compose -f tools/docker-compose.yml run es_redis

### Restart one service

Docker compose can modifying an existing deployment, this can be particularly
effective when you modify and build the backend and want to restart it without
changing anything else:

    docker-compose -f tools/docker-compose.yml up -d --no-deps es_backend


## Scaling

You can run additional worker containers by scaling with docker-compose:

    docker-compose -f tools/docker-compose.yml scale es_worker=2


