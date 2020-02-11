
Logging
=======


The entity service uses the standard Python logging library for logging.

The following named loggers are used:

* `entityservice`
  * `entityservice.views`
  * `entityservice.models`
  * `entityservice.database`
* `celery.es`

The following environment variables affect logging:

* `LOG_CFG` - sets the path to a logging configuration file. There are two examples:

  - `entityservice/default_logging.yaml`
  - `entityservice/verbose_logging.yaml`

* `DEBUG` - sets the logging level to debug for all application code.
* `LOGFILE` - directs the log output to this file instead of stdout.
* `LOG_HTTP_HEADER_FIELDS` - HTTP headers to include in the application logs.

Example logging output with `LOG_HTTP_HEADER_FIELDS=User-Agent,Host`::


    [2019-02-02 23:17:23 +0000] [10] [INFO] Adding new project to database [entityservice.views.project] Host=nginx User-Agent=python-requests/2.18.4 pid=6408f4ceb90e25cdf910b00daff3dcf23e4c891c1cfa2383 request=6c2a3730
    [2019-02-02 23:17:23 +0000] [12] [INFO] Getting detail for a project   [entityservice.views.project] Host=nginx User-Agent=python-requests/2.18.4 pid=6408f4ceb90e25cdf910b00daff3dcf23e4c891c1cfa2383 request=a7e2554a
    [2019-02-02 23:17:23 +0000] [12] [INFO] Checking credentials           [entityservice.views.project] Host=nginx User-Agent=python-requests/2.18.4 pid=6408f4ceb90e25cdf910b00daff3dcf23e4c891c1cfa2383 request=a7e2554a
    [2019-02-02 23:17:23 +0000] [12] [INFO] 0 parties have contributed hashes [entityservice.views.project] Host=nginx User-Agent=python-requests/2.18.4 pid=6408f4ceb90e25cdf910b00daff3dcf23e4c891c1cfa2383 request=a7e2554a
    [2019-02-02 23:17:23 +0000] [11] [INFO] Receiving CLK data.            [entityservice.views.project] Host=nginx User-Agent=python-requests/2.18.4 dp_id=25895 pid=6408f4ceb90e25cdf910b00daff3dcf23e4c891c1cfa2383 request=d61c3138
    [2019-02-02 23:17:23 +0000] [11] [INFO] Storing user 25895 supplied clks from json [entityservice.views.project] Host=nginx User-Agent=python-requests/2.18.4 dp_id=25895 pid=6408f4ceb90e25cdf910b00daff3dcf23e4c891c1cfa2383 request=d61c3138
    [2019-02-02 23:17:23 +0000] [11] [INFO] Received 100 encodings. Uploading 16.89 KiB to object store [entityservice.views.project] Host=nginx User-Agent=python-requests/2.18.4 dp_id=25895 pid=6408f4ceb90e25cdf910b00daff3dcf23e4c891c1cfa2383 request=d61c3138
    [2019-02-02 23:17:23 +0000] [11] [INFO] Adding metadata on encoded entities to database [entityservice.database.insertions] Host=nginx User-Agent=python-requests/2.18.4 dp_id=25895 pid=6408f4ceb90e25cdf910b00daff3dcf23e4c891c1cfa2383 request=d61c3138
    [2019-02-02 23:17:23 +0000] [11] [INFO] Job scheduled to handle user uploaded hashes [entityservice.views.project] Host=nginx User-Agent=python-requests/2.18.4 dp_id=25895 pid=6408f4ceb90e25cdf910b00daff3dcf23e4c891c1cfa2383 request=d61c3138
    [2019-02-02 23:17:24 +0000] [12] [INFO] Getting detail for a project   [entityservice.views.project] Host=nginx User-Agent=python-requests/2.18.4 pid=6408f4ceb90e25cdf910b00daff3dcf23e4c891c1cfa2383 request=c13ecc77
    [2019-02-02 23:17:24 +0000] [12] [INFO] Checking credentials           [entityservice.views.project] Host=nginx User-Agent=python-requests/2.18.4 pid=6408f4ceb90e25cdf910b00daff3dcf23e4c891c1cfa2383 request=c13ecc77
    [2019-02-02 23:17:24 +0000] [12] [INFO] 1 parties have contributed hashes [entityservice.views.project] Host=nginx User-Agent=python-requests/2.18.4 pid=6408f4ceb90e25cdf910b00daff3dcf23e4c891c1cfa2383 request=c13ecc77
    [2019-02-02 23:17:24 +0000] [10] [INFO] Receiving CLK data.            [entityservice.views.project] Host=nginx User-Agent=python-requests/2.18.4 dp_id=25896 pid=6408f4ceb90e25cdf910b00daff3dcf23e4c891c1cfa2383 request=352c4409
    [2019-02-02 23:17:24 +0000] [10] [INFO] Storing user 25896 supplied clks from json [entityservice.views.project] Host=nginx User-Agent=python-requests/2.18.4 dp_id=25896 pid=6408f4ceb90e25cdf910b00daff3dcf23e4c891c1cfa2383 request=352c4409
    [2019-02-02 23:17:24 +0000] [10] [INFO] Received 100 encodings. Uploading 16.89 KiB to object store [entityservice.views.project] Host=nginx User-Agent=python-requests/2.18.4 dp_id=25896 pid=6408f4ceb90e25cdf910b00daff3dcf23e4c891c1cfa2383 request=352c4409
    [2019-02-02 23:17:24 +0000] [10] [INFO] Adding metadata on encoded entities to database [entityservice.database.insertions] Host=nginx User-Agent=python-requests/2.18.4 dp_id=25896 pid=6408f4ceb90e25cdf910b00daff3dcf23e4c891c1cfa2383 request=352c4409
    [2019-02-02 23:17:24 +0000] [10] [INFO] Job scheduled to handle user uploaded hashes [entityservice.views.project] Host=nginx User-Agent=python-requests/2.18.4 dp_id=25896 pid=6408f4ceb90e25cdf910b00daff3dcf23e4c891c1cfa2383 request=352c4409
    [2019-02-02 23:17:25 +0000] [12] [INFO] Getting detail for a project   [entityservice.views.project] Host=nginx User-Agent=python-requests/2.18.4 pid=6408f4ceb90e25cdf910b00daff3dcf23e4c891c1cfa2383 request=8e67e62a
    [2019-02-02 23:17:25 +0000] [12] [INFO] Checking credentials           [entityservice.views.project] Host=nginx User-Agent=python-requests/2.18.4 pid=6408f4ceb90e25cdf910b00daff3dcf23e4c891c1cfa2383 request=8e67e62a
    [2019-02-02 23:17:25 +0000] [12] [INFO] 2 parties have contributed hashes [entityservice.views.project] Host=nginx User-Agent=python-requests/2.18.4 pid=6408f4ceb90e25cdf910b00daff3dcf23e4c891c1cfa2383 request=8e67e62a
    [2019-02-02 23:17:25 +0000] [12] [INFO] Adding new project to database [entityservice.views.project] Host=nginx User-Agent=python-requests/2.18.4 pid=7f302255ff3e2ce78273a390997f38ba8979965043c23581 request=df791527
    [2019-02-02 23:17:26 +0000] [12] [INFO] request description of a run   [entityservice.views.run.description] Host=nginx User-Agent=python-requests/2.18.4 pid=7f302255ff3e2ce78273a390997f38ba8979965043c23581 request=bf5b2544 rid=invalid
    [2019-02-02 23:17:26 +0000] [12] [INFO] Requested project or run resource with invalid identifier token [entityservice.views.auth_checks] Host=nginx User-Agent=python-requests/2.18.4 pid=7f302255ff3e2ce78273a390997f38ba8979965043c23581 request=bf5b2544 rid=invalid
    [2019-02-02 23:17:26 +0000] [12] [INFO] Request to delete project      [entityservice.views.project] Host=nginx User-Agent=python-requests/2.18.4 pid=7f302255ff3e2ce78273a390997f38ba8979965043c23581 request=d5b766a9
    [2019-02-02 23:17:26 +0000] [12] [INFO] Marking project for deletion   [entityservice.views.project] Host=nginx User-Agent=python-requests/2.18.4 pid=7f302255ff3e2ce78273a390997f38ba8979965043c23581 request=d5b766a9
    [2019-02-02 23:17:26 +0000] [12] [INFO] Queuing authorized request to delete project resources [entityservice.views.project] Host=nginx User-Agent=python-requests/2.18.4 pid=7f302255ff3e2ce78273a390997f38ba8979965043c23581 request=d5b766a9

With `DEBUG` enabled there are a lot of logs from the backend and workers::

    [2019-02-02 23:14:47 +0000] [10] [INFO] Marking project for deletion   [entityservice.views.project] User-Agent=python-requests/2.18.4 pid=bd0e0cf51a979f78ad8912758f20cc05d0d9129ab0f3552f request=31a6449e
    [2019-02-02 23:14:47 +0000] [10] [DEBUG] Trying to connect to postgres db [entityservice.database.util] User-Agent=python-requests/2.18.4 pid=bd0e0cf51a979f78ad8912758f20cc05d0d9129ab0f3552f request=31a6449e
    [2019-02-02 23:14:48 +0000] [10] [DEBUG] Database connection established [entityservice.database.util] User-Agent=python-requests/2.18.4 pid=bd0e0cf51a979f78ad8912758f20cc05d0d9129ab0f3552f request=31a6449e
    [2019-02-02 23:14:48 +0000] [10] [INFO] Queuing authorized request to delete project resources [entityservice.views.project] User-Agent=python-requests/2.18.4 pid=bd0e0cf51a979f78ad8912758f20cc05d0d9129ab0f3552f request=31a6449e
    [2019-02-02 23:14:48 +0000] [9] [INFO] Request to delete project      [entityservice.views.project] User-Agent=python-requests/2.18.4 pid=bd0e0cf51a979f78ad8912758f20cc05d0d9129ab0f3552f request=5486c153

Tracing
-------

`TRACING_CFG` overrides the path to an open tracing configuration file.
