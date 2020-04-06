# Anonlink Entity Service

[![Documentation Status](https://readthedocs.org/projects/anonlink-entity-service/badge/?version=stable)](https://anonlink-entity-service.readthedocs.io/en/stable/?badge=stable)

A service for performing privacy preserving record linkage. Allows organizations to carry out record linkage without disclosing personally identifiable information.

Clients should use [anonlink-client](https://github.com/data61/anonlink-client/) or the [encoding-service](https://github.com/data61/anonlink-encoding-service/).

## Documentation

Project documentation including tutorials are hosted at https://anonlink-entity-service.readthedocs.io/en/stable/
 
The [docs](./docs) folder contains the documentation source.


## Build

### Dependencies

[Docker](http://docs.docker.com/installation/) and [docker-compose](http://docs.docker.com/compose/)


### Building the docker containers

Run `./tools/build.sh` (from this directory, not from `tools`). This will create the `latest` tagged
images used by `docker-compose`.

Note docker images are pushed to Docker Hub, which can be used instead of building containers manually.


| Component        | Docker Hub |
|------------------|---------|
|  Backend/Worker  | [data61/anonlink-app](https://hub.docker.com/r/data61/anonlink-app) |
|  Nginx           | [data61/anonlink-nginx](https://hub.docker.com/r/data61/anonlink-nginx) |
|  Benchmark       | [data61/anonlink-benchmark](https://hub.docker.com/r/data61/anonlink-benchmark) |
|  Docs            | [data61/anonlink-docs-builder](https://hub.docker.com/r/data61/anonlink-docs-builder) |


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


### Testing with docker-compose

An additional docker-compose config file can be found in `./tools/ci.yml`,
this can be added to run tests along with the rest of the service:

    docker-compose -f tools/docker-compose.yml -f tools/ci.yml -p entityservicetest up -d


