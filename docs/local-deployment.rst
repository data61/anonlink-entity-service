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

The service can be accessed by connecting to port ``8851`` of the nginx container.
The local ip of the nginx container can be found with::

    docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' n1es_nginx_1

For example to `GET` the service status::

    $ export ES_NGINX_IP=`docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' n1es_nginx_1`
    $ curl $ES_NGINX_IP:8851/api/v1/status
    {
        "status": "ok",
        "number_mappings": 0,
        "rate": 1
    }


To expose the service on the host simply modify the ``docker-compose.yml`` file from::

      nginx:
        image: quay.io/n1analytics/entity-nginx
        ports:
          - 8851


to::

      nginx:
        image: quay.io/n1analytics/entity-nginx
        ports:
          - "8851:8851"


Which will bind to the host's port.

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


Local Scaling
~~~~~~~~~~~~~

You can run additional worker containers by scaling with docker-compose:

    docker-compose -f tools/docker-compose.yml scale es_worker=2


