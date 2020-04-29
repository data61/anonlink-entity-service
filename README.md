# Anonlink Entity Service

[![Documentation Status](https://readthedocs.org/projects/anonlink-entity-service/badge/?version=stable)](https://anonlink-entity-service.readthedocs.io/en/stable/?badge=stable)
[![Build Status](https://dev.azure.com/data61/Anonlink/_apis/build/status/data61.anonlink-entity-service?branchName=develop)](https://dev.azure.com/data61/Anonlink/_build/latest?definitionId=1&branchName=develop)

A REST service for performing privacy preserving record linkage. Allows organizations to carry out record linkage 
without disclosing personally identifiable information.

The *Anonlink Entity Service* is based on the concept of comparing *Anonymous Linking Codes* (ALC) - bit-arrays
representing an entity.

## Features

- Highly scalable architecture, able to distribute work to many machines at once.
- Optimized low level comparison code (provided by [anonlink](https://github.com/data61/anonlink))
- Support for client side blocking (provided by [blocklib](https://github.com/data61/blocklib))
 

Data providers wanting to link their records may want to consider using
[anonlink-client](https://github.com/data61/anonlink-client/) or the 
[encoding-service](https://github.com/data61/anonlink-encoding-service/).

## Documentation

Project documentation including tutorials are hosted at 
[anonlink-entity-service.readthedocs.io](https://anonlink-entity-service.readthedocs.io/en/stable/). 

## Demo

A demo deployment is available at [anonlink.easd.data61.xyz](https://anonlink.easd.data61.xyz/)

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
|  E2E Tests       | [data61/anonlink-test](https://hub.docker.com/r/data61/anonlink-test) |
|  Nginx Proxy     | [data61/anonlink-nginx](https://hub.docker.com/r/data61/anonlink-nginx) |
|  Benchmark       | [data61/anonlink-benchmark](https://hub.docker.com/r/data61/anonlink-benchmark) |
|  Docs            | [data61/anonlink-docs-builder](https://hub.docker.com/r/data61/anonlink-docs-builder) |


## Running Locally

See the docs for more complete deployment documentation:

- [Local Deployment](./docs/local-deployment.rst)
- [Production Deployment](./docs/production-deployment.rst)

To test locally with `docker-compose`:

    docker-compose -f tools/docker-compose.yml up

## Testing

### Testing with docker-compose

An additional docker-compose config file can be found in `./tools/ci.yml`,
this can be added to run tests along with the rest of the service:

    docker-compose -f tools/docker-compose.yml -f tools/ci.yml up -d


## Citing

The Anonlink Entity Service, and the wider Anonlink project is designed, developed and supported by 
[CSIRO's Data61](https://www.data61.csiro.au/). If you use any part of this library in your research, please 
cite it using the following BibTex entry::

    @misc{Anonlink,
      author = {CSIRO's Data61},
      title = {Anonlink Private Record Linkage System},
      year = {2017},
      publisher = {GitHub},
      journal = {GitHub Repository},
      howpublished = {\url{https://github.com/data61/anonlink-entity-service}},
    }
