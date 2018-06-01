
.. _changelog:

Changelog
=========

Version 1.8 (2018-06-01)
------------------------

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

Version 1.7.3 (2018-03-16)
--------------------------

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

Version 1.7.2 (2018-01-09)
--------------------------

Dependency and deployment updates.
We now pin versions of Python, anonlink, clkhash, phe and docker images nginx and postgres.


Version 1.7.0 (2017-10-10)
--------------------------

Added a view type that returns similarity scores of potential matches.


Version 1.6.8 (2017-08-21)
--------------------------

Scalability sprint.

 - Much better chunking of work.
 - Security hardening by modifing the response from the server. Now there is no differences between `invalid token` and `unknown resource` - both return a `403` response status.
 - Mapping information includes the time it was started.
 - Update and add tests.
 - Update the deployment to use `Helm`.
 
