Devops
===========

.. toctree::
   :maxdepth: 2

   index
   

Azure Pipeline
--------------

``entity-service`` is automatically built and tested using Azure Pipeline
in the project `Anonlink <https://dev.azure.com/data61/Anonlink>`.

It consists only of a `build pipeline <https://dev.azure.com/data61/Anonlink/_build?definitionId=1>`.

The build pipeline is described by the script `azurePipeline.yml`
which is using resources from the folder `.azurePipeline`.
Mainly, it:

- builds and pushes docker images
  - the frontend ``data61/anonlink-nginx``
  - the backend ``data61/anonlink-app``
  - the tutorials ``data61/anonlink-docs-tutorials`` (used to tests the tutorial Python Notebooks)
  - the benchmark ``data61/anonlink-benchmark`` (used to run the benchmark)
- runs the benchmark using ``docker-compose`` and publishes the artiafct in Azure
- runs the tutorial tests using ``docker-compose`` and publishes the results in Azure
- runs the integration tests by deploying the whole service on ``Kubernetes``, runs the tests and publishes the results in Azure.   

The build pipeline is triggered for every push on every branch. It is not triggered by Pull
Requests not to build twice the same commit.

The build pipeline requires two environment variables provided by Azure environment:

- `dockerHubId`: username for the pipeline to push images to Data61 dockerhub
- `dockerHubPassword`: password for the corresponding username (this is a secret variable).

It also requires a secret file (given in the Azure `Library` tab) containing the ``aws`` cluster
configuration used by ``kubectl``.

