
.. _changelog:

Changelog
=========

Next Release
------------

- Redis can now be used in highly available mode.

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
 
