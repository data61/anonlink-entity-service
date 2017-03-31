Local Deployment
================

Dependencies
~~~~~~~~~~~~

`Docker <http://docs.docker.com/installation/>`__ and
`docker-compose <http://docs.docker.com/compose/>`__

Build
~~~~~

From the folder ``deploy/entity-service``, run

::

    ./tools/build.sh

The will create the images used by ``docker-compose``.

Run
~~~~

Run docker compose:

::

    docker-compose -f tools/docker-compose.yml up

This will start the following containers:

-  nginx frontend (named ``tools_es_nginx_1``)
-  gunicorn/flask backend (named ``tools_es_backend_1``)
-  celery backend worker (named ``tools_es_worker_1``)
-  postgres database (named ``tools_es_db_1``)
-  redis job queue (named ``tools_es_redis_1``)

All these containers will be on the docker network ``tools_es_network``.

The service should be exposed on port ``8851`` of the host machine.

Testing with docker-compose
----

An additional docker-compose config file can be found in `./tools/ci.yml`,
this can be added in to run along with the rest of the service::

    docker-compose -f tools/docker-compose.yml -f ci.yml -p entityservicetest up -d


# Data generation

::

    docker run -it \
        -v <place-to-put-generated-data>:/var/www/data \
        -e ENTITY_SERVICE_TEST_SIZE=10000 \
        quay.io/n1analytics/entity-app python generate_test_data.py

Note: the folder in which the generated data will be stored needs to exist.


Development Tips
----

Volumes
~~~~

You might need to destroy the docker volumes used for the object store
and the postgres database:

    docker-compose -f tools/docker-compose.yml rm --all


Restart one service
~~~~

Docker compose can modifying an existing deployment, this can be particularly
effective when you modify and build the backend and want to restart it without
changing anything else:

    docker-compose -f tools/docker-compose.yml up -d --no-deps es_backend


Scaling
~~~~

You can run additional worker containers by scaling with docker-compose:

    docker-compose -f tools/docker-compose.yml scale es_worker=2


