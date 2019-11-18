
.. _changelog:

Changelog
=========

Next Version
------------

- fixed a bug where a dataprovider could upload her clks multiple time in a project using the same upload token (#463)
- modify ``similarity_score`` output to follow the group format, which will simplify extending this output type to more parties (#464)

Breaking Change
~~~~~~~~~~~~~~~

- the ``dataproviders`` table `uploaded` field has been modified from a BOOL to an ENUM type (#463)
- the ``similarity_score`` output type has been modified, it now returns a JSON array of JSON objects, where such an object
  looks like `[[party_id_0, row_index_0], [party_id_1, row_index_1], score]`. (#464)

Version 1.13.0-alpha
--------------------

- fixed bug where invalid state changes could occur when starting a run (#459)
- ``matching`` output type has been removed as redundant with the ``groups`` output with 2 parties. (#458)

- Update dependencies:

    - requests from 2.21.0 to 2.22.0 (#459)
    
Breaking Change
~~~~~~~~~~~~~~~

- ``matching`` output type is not available anymore. (#458)


Version 1.12.0
--------------

- Logging configurable in the deployed entity service by using the key ``loggingCfg``. (#448)
- Several old settings have been removed from the default values.yaml and docker
  files which have been replaced by ``CHUNK_SIZE_AIM`` (#414):

   - ``SMALL_COMPARISON_CHUNK_SIZE``
   - ``LARGE_COMPARISON_CHUNK_SIZE``
   - ``SMALL_JOB_SIZE``
   - ``LARGE_JOB_SIZE``

- Remove ``ENTITY_MATCH_THRESHOLD`` environment variable (#444)
- Celery configuration updates to solve threads and memory leaks in deployment. (#427)
- Update docker-compose files to use these new preferred configurations.
- Update helm charts with preferred configuration default deployment is a minimal working deployment.
- New environment variables: ``CELERY_DB_MIN_CONNECTIONS``, ``FLASK_DB_MIN_CONNECTIONS``, ``CELERY_DB_MAX_CONNECTIONS``
  and ``FLASK_DB_MAX_CONNECTIONS`` to configure the database connections pool. (#405)
- Simplify access to the database from services relying on a single way to get a connection via a connection pool. (#405)
- Deleting a run is now implemented. (#413)
- Added some missing documentation about the output type `groups` (#449)
- Sentinel name is configurable. (#436)
- Improvement on the Kubernetes deployment test stage on Azure DevOps:

   - Re-order cleaning steps to first purge the deployment and then deleting the remaining. (#426)
   - Run integration tests in parallel, reducing pipeline stage `Kubernetes deployment tests` from 30 minutes to 15 minutes. (#438)
   - Tests running on a deployed entity-service on k8s creates an artifact containing all the logs of all the containers, useful for debugging. (#445)
   - Test container not restarted on test failure. (#434)

- Benchmark improvements:

   - Benchmark output has been modified to handle multi-party linkage.
   - Benchmark to handle more than 2 parties, being able to repeat experiments.
     and pushing the results to minio object store. (#406, #424 and #425)
   - Azure DevOps benchmark stage runs a 3 parties linkage. (#433)

- Improvements on Redis cache:

   - Refactor the cache. (#430)
   - Run state kept in cache (instead of fully relying on database) (#431 and #432)

- Update dependencies:

   - anonlink to v0.12.5. (#423)
   - redis from 3.2.0 to 3.2.1 (#415)
   - alpine from 3.9 to 3.10.1 (#404)

- Add some release documentation. (#455)

Version 1.11.2
--------------

- Switch to Azure Devops pipeline for CI.
- Switch to docker hub for container hosting.

Version 1.11.1
--------------

- Include multiparty linkage tutorial/example.
- Tightened up how we use a database connection from the flask app.
- Deployment and logging documentation updates.

Version 1.11.0
--------------

- Adds support for multiparty record linkage.
- Logging is now configurable from a file.

Other improvements
~~~~~~~~~~~~~~~~~~

- Another tutorial for directly using the REST api was added.
- K8s deployment updated to use ``3.15.0`` Postgres chart.
  Postgres configuration now uses a ``global`` namespace
  so subcharts can all use the same configuration as documented
  `here <https://github.com/helm/charts/tree/master/stable/postgresql#use-of-global-variables>`_.
- Jenkins testing now fails if the benchmark exits incorrectly or if the benchmark
  results contain failed results.
- Jenkins will now execute the tutorials notebooks and fail if any cells error.


Version 1.10.0
--------------

- Updates Anonlink and switches to using Anonlink's default format for serialization
  of similarity scores.
- Sorts similarity scores before solving, improving accuracy.
- Uses Anonlink's new API for similarity score computation and solving.
- Add support for using an external Postgres database.
- Added optional support for redis discovery via the sentinel protocol.
- Kubernetes deployment no longer includes a default postgres password.
  Ensure that you set your own `postgresqlPassword`.
- The Kubernetes deployment documentation has been extended.

Version 1.9.4
-------------

- Introduces configurable logging of HTTP headers.
- Dependency issue resolved.

Version 1.9.3
-------------

- Redis can now be used in highly available mode. Includes upstream fix where the redis sentinels crash.
- The custom kubernetes certificate management templates have been removed.
- Minor updates to the kubernetes resources. No longer using beta apis.

Version 1.9.2
-------------

- 2 race conditions have been identified and fixed.
- Integration tests are sped up and more focused. The test suite now fails after the first test failure.
- Code tidy-ups to be more pep8 compliant.

Version 1.9.1
-------------

- Adds support for (almost) arbitrary sized encodings. A minimum and maximum can be set at deployment time, and
  currently anonlink requires the size to be a multiple of 8.
- Adds support for `opentracing <https://opentracing.io/>`_ with Jaeger.
- improvements to the benchmarking container
- internal refactoring of tasks

Version 1.9.0
-------------

- minio and redis services are now optional for kubernetes deployment.
- Introduction of a high memory worker and associated task queue.
- Fix issue where we could start tasks twice.
- Structlog now used for celery workers.
- CI now tests a kubernetes deployment.
- Many Jenkins CI updates and fixes.
- Updates to Jupyter notebooks and docs.
- Updates to Python and Helm chart dependencies and docker base images.


Version 1.8.1
-------------

Improve system stability while handling large intermediate results.
Intermediate results are now stored in files instead of in Redis. This permits us to stream them instead of loading
everything into memory.


Version 1.8
-----------

Version 1.8 introduces breaking changes to the REST API to allow an analyst to reuse uploaded CLKs.

Instead of a linkage project only having one result, we introduce a new sub-resource `runs`. A project holds the schema
and CLKs from all data providers; and multiple runs can be created with different parameters. A run has a status and a
result endpoint. Runs can be queued before the CLK data has been uploaded.

We also introduced changes to the result types.
The result type `permutation`, which was producing permutations and an encrypted mask, was removed. 
And the result type `permutation_unecrypyted_mask` was renamed to `permutations`.

Brief summary of API changes:
- the `mapping` endpoint has been renamed to `projects`
- To carry out a linkage computation you must post to a project's `runs` endpoint: `/api/v1/project/<PROJECT_ID>/runs
- Results are now accessed under the `runs` endpoint: `/api/v1/project/<PROJECT_ID>/runs/<RUN_ID>/result`
- result type `permutation_unecrypyted_mask` was renamed to `permutations`
- result type `permutation` was removed

For all the updated API details check the `Open API document <./api.html>`_.

Other improvements
~~~~~~~~~~~~~~~~~~

- The documentation is now served at the root.
- The flower monitoring tool for celery is now included with the docker-compose deployment.
  Note this will be disabled for production deployment with kubernetes by default.
- The docker containers have been migrated to alpine linux to be much leaner.
- Substantial internal refactoring - especially of views.
- Move to pytest for end to end tests.

Version 1.7.3
-------------

Deployment and documentation sprint.

- Fixes a bug where only the top `k` results of a chunk were being requested from anonlink. #59 #84
- Updates to helm deployment templates to support a single namespace having multiple entityservices. Helm
  charts are more standard, some config has moved into a configmap and an experimental cert-manager
  configuration option has been added. #83, #90
- More sensible logging during testing.
- Every http request now has a (globally configurable) timeout
- Minor update regarding handling uploading empty CLKs. #92
- Update to latest versions of anonlink and clkhash. #94
- Documentation updates.

Version 1.7.2
-------------

Dependency and deployment updates.
We now pin versions of Python, anonlink, clkhash, phe and docker images nginx and postgres.


Version 1.7.0
-------------

Added a view type that returns similarity scores of potential matches.


Version 1.6.8
-------------

Scalability sprint.

 - Much better chunking of work.
 - Security hardening by modifing the response from the server. Now there is no differences between `invalid token` and `unknown resource` - both return a `403` response status.
 - Mapping information includes the time it was started.
 - Update and add tests.
 - Update the deployment to use `Helm`.
 
