# anonlink 

Allows two organizations to carry out private record linkage - without
disclosing personally identifiable information.


## Documentation

The [docs](./docs) folder contains the service's documentation. A high level 
description of the service is available in [docs/index.rst](./docs/index.rst).


### Building the docs

To build and serve the html docs run:

    pip install -r docs/doc-requirements.txt
    sphinx-build -b html docs n1esdocs
    cd n1esdocs
    python -m http.server


or using docker:

    docker run -it -v <PATH TO PROJECT>:/src -v <OUTPUT HTML PATH>:/build quay.io/n1analytics/entity-docs
    

## Build

### Dependencies

[Docker](http://docs.docker.com/installation/) and [docker-compose](http://docs.docker.com/compose/)


### Building the docker containers

Run `./tools/build.sh` (from this directory, not from `tools`). This will create the tagged
images used by `docker-compose`.

Note developers should have quay.io credentials - in which case you can skip this step and 
docker will pull the latest images when you start the service.

| Component       | Quay.io |
|-----------------|---------|
|  Backend/Worker | [![Backend Docker Repository on Quay](https://quay.io/repository/n1analytics/entity-app/status?token=ec8444d6-f940-4dcf-a840-2a077f56fb1b "Backend Docker Repository on Quay")](https://quay.io/repository/n1analytics/entity-app)         |
|  Nginx          |  [![Nginx Docker Repository on Quay](https://quay.io/repository/n1analytics/entity-nginx/status?token=f669c554-1852-45bc-b595-29bb902a911a "Nginx Docker Repository on Quay")](https://quay.io/repository/n1analytics/entity-nginx)
       |
| Benchmark       |  [![Docker Repository on Quay](https://quay.io/repository/n1analytics/entity-benchmark/status?token=642a6f47-e8db-4714-9508-f6f209915e33 "Docker Repository on Quay")](https://quay.io/repository/n1analytics/entity-benchmark)       |
| Docs            |  [![Docs Builder Docker Repository on Quay](https://quay.io/repository/n1analytics/entity-docs/status?token=38232319-38cb-4749-91ef-1bdca20c4363 "Docs Builder Docker Repository on Quay")](https://quay.io/repository/n1analytics/entity-docs)
       |


## Running Locally

See the docs for more complete deployment documentation:

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

With docker you can run benchmarks against the service:

    docker run -it \
        -e SERVER=<ENTITY-SERVER-HOST> \
        --net=host \
        quay.io/n1analytics/entity-benchmark

Note the `--net` parameter is only required if connecting to a service running locally
with docker compose. If the network is not recognized, use `docker network ls` to
see the available docker networks and find which network was created by docker-compose.

### Testing with docker-compose

An additional docker-compose config file can be found in `./tools/ci.yml`,
this can be added to run tests along with the rest of the service:

    docker-compose -f tools/docker-compose.yml -f tools/ci.yml -p entityservicetest up -d

## Development Tips

There are two libraries `anonlink` and `clkhash` which should be installed in your 
virtual environment for local development.


### Volumes

You might need to destroy the docker volumes used for the object store
and the postgres database:

    docker-compose -f tools/docker-compose.yml rm --all

