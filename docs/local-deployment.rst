Local Deployment
================

Dependencies
~~~~~~~~~~~~

`Docker <http://docs.docker.com/installation/>`__ and
`docker-compose <http://docs.docker.com/compose/>`__

Build
~~~~~

From the project folder, run::

    ./tools/build.sh

The will create the docker images tagged with `latest` which are used by ``docker-compose``.

Run
~~~~

Run docker compose::

    docker-compose -p n1es -f tools/docker-compose.yml up

This will start the following containers:

-  nginx frontend (named ``n1es_nginx_1``)
-  gunicorn/flask backend (named ``n1es_backend_1``)
-  celery backend worker (named ``n1es_worker_1``)
-  postgres database (named ``n1es_db_1``)
-  redis job queue (named ``n1es_redis_1``)
-  minio object store

The REST api for the service is exposed on port ``8851`` of the nginx container, which docker
will map to a high numbered port on your host.

The address of the nginx endpoint can be found with::

    docker port n1es_nginx_1 "8851"

For example to `GET` the service status::

    $ export ENTITY_SERVICE=`docker port n1es_nginx_1 "8851"`
    $ curl $ENTITY_SERVICE/api/v1/status
    {
        "status": "ok",
        "number_mappings": 0,
        "rate": 1
    }

The service can be taken down by hitting CTRL+C. This doesn't clear
the DB volumes, which will persist and conflict with the next call to
`docker-compose ... up` unless they are removed.  Removing these
volumes is easy, just run::

    docker-compose -p n1es -f tools/docker-compose.yml down -v

in between calls to `docker-compose ... up`.

Testing with docker-compose
---------------------------

An additional docker-compose config file can be found in `./tools/ci.yml`,
this can be added in to run along with the rest of the service::

    docker-compose -p n1estest -f tools/docker-compose.yml -f tools/ci.yml  up -d

    docker logs -f n1estest_ci_1

    docker-compose -p n1estest -f tools/docker-compose.yml -f tools/ci.yml down

Data generation
---------------

::

    docker run -it \
        -v <place-to-put-generated-data>:/var/www/data \
        -e ENTITY_SERVICE_TEST_SIZE=10000 \
        quay.io/n1analytics/entity-app python generate_test_data.py

Note: the folder in which the generated data will be stored needs to exist.


Docker Compose Tips
-------------------

Local Scaling
~~~~~~~~~~~~~

You can run additional worker containers by scaling with docker-compose:

    docker-compose -f tools/docker-compose.yml scale es_worker=2


A collection of development tips.

Volumes
~~~~~~~

You might need to destroy the docker volumes used for the object store
and the postgres database::

    docker-compose -f tools/docker-compose.yml rm -s -v [-p <project-name>]


Restart one service
~~~~~~~~~~~~~~~~~~~

Docker compose can modify an existing deployment, this can be particularly
effective when you modify and rebuild the backend and want to restart it without
changing anything else::

    docker-compose -f tools/docker-compose.yml up -d --no-deps es_backend


Scaling
~~~~~~~

You can run additional worker containers by scaling with docker-compose::

    docker-compose -f tools/docker-compose.yml scale es_worker=2



Mix and match docker compose
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

During development you can run the redis and database containers with
docker-compose, and directly run the celery and flask applications with Python.

::

    docker-compose -f tools/docker-compose.yml run es_db
    docker-compose -f tools/docker-compose.yml run es_redis
