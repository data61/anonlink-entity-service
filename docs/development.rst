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


Testing Local Deployment
~~~~~~~~~~~~~~~~~~~~~~~~

The docker compose file ``tools/ci.yml`` is deployed along with ``tools/docker-compose.yml``. This simply defines an
additional container (from the same backend image) which runs the integration tests after a short delay.

The logs from the various containers (nginx, backend, worker, database) are all collected, archived and are made
available in the Jenkins UI for introspection.


Testing K8s Deployment
~~~~~~~~~~~~~~~~~~~~~~

The kubernetes deployment uses ``helm`` with the template found in ``deployment/entity-service``. Jenkins additionally
defines the docker image versions to use and ensures an ingress is not provisioned. The deployment is configured to be
quite conservative in terms of cluster resources. Currently this logic all resides in ``Jenkinsfile.groovy``.

The k8s deployment test is limited to 30 minutes and an effort is made to clean up all created resources.

After a few minutes waiting for the deployment a `Kubernetes Job <https://kubernetes.io/docs/concepts/workloads/controllers/jobs-run-to-completion/>`__ is created using ``kubectl create``.

This job includes a ``1GiB`` `persistent volume claim <https://kubernetes.io/docs/concepts/storage/persistent-volumes/>`__
to which the results are written (as ``results.xml``). During the testing the pytest output will be rendered in jenkins,
and then the Job's pod terminates. We create a temporary pod which mounts the same results volume and then we copy
across the produced artifact for rendering in Jenkins. This dance is only necessary to retrieve files from the cluster
to our Jenkins instance, it would be straightforward if we only wanted the stdout from each pod/job.


