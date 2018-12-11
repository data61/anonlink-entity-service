Benchmarking
============

In the `benchmarking` folder is a benchmarking script and associated Dockerfile.
The docker image is published at ``https://quay.io/repository/n1analytics/entity-benchmark``

The container/script is configured via environment variables.

- ``SERVER``: (required) the url of the server.
- ``EXPERIMENT``: json file containing a list of experiments to run. Schema of experiments is
  defined in `./schema/experiments.json`.
- ``DATA_PATH``: path to a directory to store test data (useful to cache).
- ``RESULT_PATH``: full filename to write results file.
- ``SCHEMA``: path to the linkage schema file used when creating projects. If not provided it is assumed
  to be in the data directory.
- ``TIMEOUT``: this timeout defined the time to wait for the result of a run in seconds. Default is 1200 (20min).


Run Benchmarking Container
--------------------------

Run the container directly with docker - substituting configuration information as required::

    docker run -it
        -e SERVER=https://testing.es.data61.xyz \
        -e RESULTS_PATH=/app/results.json \
        quay.io/n1analytics/entity-benchmark:latest


By default the container will pull synthetic datasets from an S3 bucket and run default benchmark experiments
against the configured ``SERVER``. The default experiments (listed below) are set in
``benchmarking/default-experiments.json``.

The output will be printed and saved to a file pointed to by ``RESULTS_PATH`` (e.g. to ``/app/results.json``).

Cache Volume
~~~~~~~~~~~~

For speeding up benchmarking when running multiple times you may wish to mount a volume at the ``DATA_PATH``
to store the downloaded test data. Note the container runs as user ``1000``, so any mounted volume must be read
and writable by that user. To create a volume using docker::

    docker volume create linkage-benchmark-data

To copy data from a local directory and change owner::

    docker run --rm -v `pwd`:/src \
        -v linkage-benchmark-data:/data busybox \
        sh -c "cp -r /src/linkage-bench-cache-experiments.json /data; chown -R 1000:1000 /data"

To run the benchmarks using the cache volume::

    docker run \
        --name ${benchmarkContainerName} \
        --network ${networkName} \
        -e SERVER=${localserver} \
        -e DATA_PATH=/cache \
        -e EXPERIMENT=/cache/linkage-bench-cache-experiments.json \
        -e RESULTS_PATH=/app/results.json \
        --mount source=linkage-benchmark-data,target=/cache \
        quay.io/n1analytics/entity-benchmark:latest


Experiments
-----------

Experiments to run can be configured as a simple json document. The default is::

    [
      {
        "sizes": ["100K", "100K"],
        "threshold": 0.95
      },
      {
        "sizes": ["100K", "100K"],
        "threshold": 0.80
      },
      {
        "sizes": ["100K", "1M"],
        "threshold": 0.95
      }
    ]

The schema of the experiments can be found in ``benchmarking/schema/experiments.json``.

