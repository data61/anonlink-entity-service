
.. _changelog:

Changelog
=========

Next Version
------------
**Custom Celery Routes**

Added support to customise the celery routing with environment variable `CELERY_ROUTES`.

Version 1.15.1
--------------

**Dependency updates**

Implemented in #687

**Delete upload files on object store after ingestion**

If a data provider uploads its data via the object store, we now clean up afterwards.

Implemented in #686

**Fixed Record Linkage API tutorial**

Adjusted to changes in the clkhash library.

Implemented in #684

**Delete encodings from database at project deletion**

Encodings will be deleted at project deletion, but only for projects created with this version or higher.

Implemented in #683

Version 1.15.0
---------------

Highlights
~~~~~~~~~~

**Similarity scores are deduplicated**

Previously candidate pairs that appear in more than one block would produce more than one similarity score.
The iterator that processing similarity scores now de-duplicates before storing them.

Implemented in: #660

**Provided Block Identifiers are now hashed**

We now hash the user provided block identifier before storing in DB.

Implemented in: #633

**Failed runs return message indicating the failure reason**

The run status for a failed run now includes a `message` attribute with information on what went wrong.

Implemented in: #624

Other changes
~~~~~~~~~~~~~

The run status endpoint now includes `total_number_of_comparisons` for completed runs.
Implemented in: #651

As usual lots of version upgrades - now using the latest stable redis and postgresql.

Version 1.14.0
---------------


Highlights
~~~~~~~~~~

**API now supports directly downloading similarity scores from the internal object store**

If the request includes the header `RETURN-OBJECT-STORE-ADDRESS`, the response will be a small json payload with
temporary download credentials to pull the _binary_ similarity scores directly from the object store. The json object
has `credentials` and `object` keys::

    {
      "credentials": {
        "AccessKeyId": "",
        "SecretAccessKey": "",
        "SessionToken": "",
        "Expiration": "<ISO 8601 datetime string>"
      },
      "object": {
          "endpoint": "<config.DOWNLOAD_OBJECT_STORE_SERVER>",
          "secure": "<config.DOWNLOAD_OBJECT_STORE_SECURE>",
          "bucket": "bucket_name",
          "path": "path"
      }
    }



The binary file is serialized using ``anonlink.serialization``, you can convert the stream into Python types with::

        mc = Minio(file_info['endpoint'], ...)
        candidate_pair_stream = mc.get_object(file_info['bucket'], file_info['path'])
        sims, (dset_is0, dset_is1), (rec_is0, rec_is1) = anonlink.serialization.load_candidate_pairs(candidate_pair_stream)


The following settings control the optional feature of using an external object store:

=======================================  ==========================================
     Environment Variable                 Helm Config
=======================================  ==========================================
``DOWNLOAD_OBJECT_STORE_SERVER``         ``anonlink.objectstore.downloadServer``
``DOWNLOAD_OBJECT_STORE_SECURE``         ``anonlink.objectstore.downloadSecure``
``DOWNLOAD_OBJECT_STORE_ACCESS_KEY``     ``anonlink.objectstore.downloadAccessKey``
``DOWNLOAD_OBJECT_STORE_SECRET_KEY``     ``anonlink.objectstore.downloadSecretKey``
``DOWNLOAD_OBJECT_STORE_STS_DURATION``   ``-`` (default 43200 seconds)
=======================================  ==========================================

Implemented in: #594, #612, #613, #614

**Service now uses sqlalchemy for database migrations**

Sqlalchemy models have been added for all database tables, initial database setup
now uses alembic for migrations. The database and object store init scripts can now
be run multiple times without causing issues.

Implemented in #603, #611

**New configurable limits on maximum number of candidate pairs**

Protects the service from running out of memory due to excessive numbers of
candidate pairs being processed. An added side effect is the service now keeps
track of the number of candidate pairs in a run (as well as the number of comparisons).

The configurable is controlled by the following two environment variables, and their initial
default values::

    SOLVER_MAX_CANDIDATE_PAIRS="100_000_000"
    SIMILARITY_SCORES_MAX_CANDIDATE_PAIRS="500_000_000"


If a run exceeds these limits, the run is put into an error state and further processing is
abandoned to protect the service from running out of memory.

Implemented in #595, #605

Other changes
~~~~~~~~~~~~~

- Ingress now supports a user supplied path. We no longer assume an nginx ingress controller. #587
- Migrate off deprecated k8s chart repos #596, #588
- Helm chart now uses standard recommended Kubernetes labels. #616
- Fix an issue with case sensitivity in object store metadata #590
- If the object store bucket doesn't exist it is now automatically created. #577
- Ignore but log failures to delete from object store #576
- Many dependency updates #578, #579, #580, #582, #581, #583, #596, #604, #609, #615
- Update the base image, all base dependencies and migrated from minio-py v5 to v7 #601, #608, #610
- CI e2e tests on Kubernetes will now correctly fail if the tests don't run. #618
- Add optional pod annotations to init jobs. #619

Version 1.13.0
--------------

- extended tutorial to include upload to object store #573
- chart update #572

Version 1.13.0-beta3
--------------------

- Improved performance for blocks of small size #563
- fix a problem with the upload to the external object store #564
- updated documentation #567, $569

Version 1.13.0-beta2
--------------------

Adds support for users to supply blocking information along with encodings. Data can now be uploaded to
an object store and pulled by the Anonlink Entity Service instead of uploaded via the REST API.
This release includes substantial internal changes as encodings are now stored in Postgres instead of
the object store.

- Feature to pull data from an object store and create temporary upload credentials. #537, #544, #551
- Blocking implementation #510 #527,
- Benchmarking #478, #541
- Encodings are now stored in Postgres database instead of files in an object store. #516, #522
- Start to add integration tests to complement our end to end tests. #520, #528
- Use anonlink-client instead of clkhash #536
- Use Python 3.8 in base image. #518
- A base image is now used for all our Docker images. #506, #511, #517, #519
- Binary encodings now stored internally with their encoding id. #505
- REST API implementation for accepting clknblocks #503
- Update Open API spec to version 3. Add Blocking API #479
- CI Updates #476
- Chart updates #496, #497, #539
- Documentation updates (production deployment, debugging with PyCharm) #473, #504
- Fix Jaeger #500, #523

Misc changes/fixes:
- Detect invalid encoding size as early as possible #507
- Use local benchmark cache #531
- Cleanup docker-compose #533, #534, #547
- Calculate number of comparisons accounting for user supplied blocks. #543

Version 1.13.0-beta
-------------------

- Fixed a bug where a dataprovider could upload their clks multiple times in a project using the same upload token. (#463)
- Fixed a bug where workers accepted work after failing to initialize their database connection pool. (#477)
- Modified ``similarity_score`` output to follow the group format in preparation to extending this output type to more
  parties. (#464)
- Tutorials have been improved following an internal review. (#467)
- Database schema and CLK upload api has been modified to support blocking. (#470)
- Benchmarking results can now be saved to an object store without authentication. Allowing an AWS user to save to S3
  using node permissions. (#490)
- Removed duplicate/redundant tests. (#466)
- Updated dependencies:

    - We have enabled `dependabot <https://dependabot.com/>`_ on GitHub to keep our Python dependencies up to date.
    - ``anonlinkclient`` now used for benchmarking. (#490)
    - Chart dependencies ``redis-ha``, ``postgres`` and ``minio`` all updated. (#496, #497)

Breaking Changes
~~~~~~~~~~~~~~~~

- the ``similarity_score`` output type has been modified, it now returns a JSON array of JSON objects, where such an object
  looks like ``[[party_id_0, row_index_0], [party_id_1, row_index_1], score]``. (#464)
- Integration test configuration is now consistent with benchmark config. Instead of setting ``ENTITY_SERVICE_URL`` including
  ``/api/v1`` now just set the host address in ``SERVER``. (#495)


Database Changes (Internal)
~~~~~~~~~~~~~~~~~~~~~~~~~~~

- the ``dataproviders`` table ``uploaded`` field has been modified from a BOOL to an ENUM type (#463)
- The ``projects`` table has a new ``uses_blocking`` field. (#470)

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
 
