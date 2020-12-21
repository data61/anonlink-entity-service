Development
===========

.. toctree::
   :maxdepth: 1

   changelog
   devops
   debugging
   future
   releasing


Implementation Details
----------------------

Components
~~~~~~~~~~

The entity service is implemented in Python and comprises the following
components:

-  A gunicorn/flask backend that implements the HTTP REST api.
-  Celery backend worker/s that do the actual work. This interfaces with
   the ``anonlink`` library.
-  An nginx frontend to reverse proxy the gunicorn/flask backend
   application.
-  A Minio object store (large files such as raw uploaded hashes, results)
-  A postgres database stores the linking metadata.
-  A redis task queue that interfaces between the flask app and the
   celery backend. Redis also acts as an ephemeral cache.

Each of these has been packaged as a docker image, however the use of
external services (redis, postgres, minio) can be configured through environment
variables. Multiple workers can be used to distribute the work beyond
one machine - by default all cores will be used for computing similarity
scores and encrypting the mask vector.

.. _dev-dependencies:

Dependencies
~~~~~~~~~~~~

Anonlink Entity Service uses Python dependencies found in ``base/requirements.txt``. These can be
manually installed using ``pip``::

    pip install -r base/requirements.txt


Docker is used for packaging the application, we rely on a base image that includes the operating system
level and Python level dependencies. To update a dependency change the pinned version in ``base/requirements.txt``
or ``base/Dockerfile``. Our CI system will bake the base image and tag it with a digest.

If you were so inclined you could generate the digest yourself with bash (example digest shown)::

    $ cd base
    $ sha256sum requirements.txt Dockerfile | sha256sum | cut -f 1 -d " " | tr [:upper:] [:lower:]
    3814723844e4b359f0b07e86a57093ad4f88aa434c42ced9c72c611bbcf9819a

Then a microservice can be updated to use this base image. In the application ``Dockerfile`` there will
be an overridable digest::

    ARG VERSION=4b497c1a0b2a6cc3ea848338a67c3a129050d32d9c532373e3301be898920b55
    FROM data61/anonlink-base:${VERSION}


Either update this digest in the ``Dockerfile``, or when building with ``docker build`` pass in an extra
argument::

    --build-arg VERSION=3814723844e4b359f0b07e86a57093ad4f88aa434c42ced9c72c611bbcf9819a


Note the CI system automatically uses the current base image when building the application images.

Redis
-----

Redis is used as the default message broker for celery as well as a cross-container
in memory cache.

Redis key/values used directly by the Anonlink Entity Service:

+------------------------+------------+-------------------+
| Key                    | Redis Type | Description       |
+========================+============+===================+
| "entityservice-status" |    String  | pickled status    |
+------------------------+------------+-------------------+
| "run:{run_id}"         |    Hash    | run info          |
+------------------------+------------+-------------------+
| "clk-pkl-{dp_id}"      |    String  | pickled encodings |
+------------------------+------------+-------------------+


Redis Cache: Run Info
~~~~~~~~~~~~~~~~~~~~~

The run info ``HASH`` stores:

- similarity scoring progress for each run under ``"progress"``
- run state under ``"state"``, current valid states are
  ``{active, complete, deleted}``. See
  ``backend/entityservice/cache/active_runs.py`` for implementation.


Object Store
------------

Write access to an AWS S3 compatible object store is required to store intermediate files for the
Anonlink Entity Service. The optional feature for data upload via object store also requires access
to an AWS S3 compatible object store - along with authorization to create temporary credentials.

`MinIO <https://min.io/>`__ is an open source object store implementation which can be used with
both Docker Compose and Kubernetes deployments instead of AWS S3.


Deployment Testing
------------------

Testing Local Deployment
~~~~~~~~~~~~~~~~~~~~~~~~

The docker compose file ``tools/ci.yml`` is deployed along with ``tools/docker-compose.yml``. This compose file
defines additional containers which run benchmarks and tests after a short delay.


Testing K8s Deployment
~~~~~~~~~~~~~~~~~~~~~~

The kubernetes deployment uses ``helm`` with the template found in ``deployment/entity-service``. Jenkins additionally
defines the docker image versions to use and ensures an ingress is not provisioned. The deployment is configured to be
quite conservative in terms of cluster resources.

The k8s deployment test is limited to 30 minutes and an effort is made to clean up all created resources.

After a few minutes waiting for the deployment a
`Kubernetes Job <https://kubernetes.io/docs/concepts/workloads/controllers/jobs-run-to-completion/>`__ is created using
``kubectl create``.

This job includes a ``1GiB`` `persistent volume claim <https://kubernetes.io/docs/concepts/storage/persistent-volumes/>`__
to which the results are written (as ``results.xml``). During the testing the pytest output will be rendered,
and then the Job's pod terminates. We create a temporary pod which mounts the same results volume and then we copy
across the produced test result artifact.
