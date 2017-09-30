# N1 Entity Matching Microservice

[![Backend Docker Repository on Quay](https://quay.io/repository/n1analytics/entity-app/status?token=ec8444d6-f940-4dcf-a840-2a077f56fb1b "Backend Docker Repository on Quay")](https://quay.io/repository/n1analytics/entity-app) [![Nginx Docker Repository on Quay](https://quay.io/repository/n1analytics/entity-nginx/status "Nginx Docker Repository on Quay")](https://quay.io/repository/n1analytics/entity-nginx)

Allows two organizations to carry out private record linkage - without
disclosing personally identifiable information.

- Deployed to https://es.data61.xyz
- Jupyter notebook with tutorial available at: https://jupyter.es.data61.xyz


## Documentation

The [docs](./docs) folder contains the services
documentation. In a release this will be html documents. These
can be served using Python's built in webserver:

    cd docs
    python -m http.server


### Building the docs

To build and serve the html docs run:

    pip install -f docs/doc-requirements.txt
    sphinx-build -b html docs n1esdocs
    cd n1esdocs
    python -m http.server

A high level description of the service is available in
the [docs](./docs/index.rst).

## Build

### Dependencies

[Docker](http://docs.docker.com/installation/) and [docker-compose](http://docs.docker.com/compose/)


### Building the docker containers

Run `./tools/build.sh` (from this directory, not from `tools`). This will create the tagged
images used by `docker-compose`.

Note developers should have quay.io credentials - in which case you can skip this step and 
docker will pull the latest images when you start the service.

## Running Locally

Note there is much more complete deployment documentation available for:

- [Local Deployment](./docs/local-deployment.rst)
- [Production Deployment](./docs/production-deployment.rst)

To run locally with `docker-compose`:

    docker-compose -f tools/docker-compose.yml up

## Testing

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

    docker-compose -f tools/docker-compose.yml -f tools/ci.yml -p entityservicetest up -d


# Data generation

    docker run -it \
        -v <place-to-put-generated-data>:/var/www/data \
        -e ENTITY_SERVICE_TEST_SIZE=10000 \
        quay.io/n1analytics/entity-app python generate_test_data.py

Note: the folder in which the generated data will be stored need to be existing.

## Development Tips

### Checking out the code

This repository uses [git submodules](https://git-scm.com/book/en/v2/Git-Tools-Submodules), so to clone
use `git clone --recursive git@github.com:n1analytics/entity-service.git` or you will have to run either
`tools/update.sh` or:

```
git submodule init
git submodule update
```

Note to update the submodule's repo, you can update to the latest master with:

```
git submodule foreach git pull origin master
```


### Volumes

You might need to destroy the docker volumes used for the object store
and the postgres database:

    docker-compose -f tools/docker-compose.yml rm --all

