Development
===========

A collection of development tips.

Volumes
-------

You might need to destroy the docker volumes used for the object store
and the postgres database::

    docker-compose -f tools/docker-compose.yml rm --all


Restart one service
-------------------

Docker compose can modifying an existing deployment, this can be particularly
effective when you modify and build the backend and want to restart it without
changing anything else:

::

    docker-compose -f tools/docker-compose.yml up -d --no-deps es_backend


Scaling
-------

You can run additional worker containers by scaling with docker-compose:

::

    docker-compose -f tools/docker-compose.yml scale es_worker=2



Mix and match docker compose
----------------------------

During development you can run the redis and database containers with
docker-compose, and directly run the celery and flask applications with Python.

::

    docker-compose -f tools/docker-compose.yml run es_db
    docker-compose -f tools/docker-compose.yml run es_redis
