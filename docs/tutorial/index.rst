Tutorials
=========

.. toctree::
   :maxdepth: 1

   cli
   Record Linkage API.ipynb
   Permutations.ipynb
   Similarity Scores.ipynb
   multiparty-linkage-with-clkhash.ipynb
   multiparty-linkage-in-entity-service.ipynb


Usage
-----

The code is often evolving and may include some breaking changes not yet deployed in our testing deployment (at the
URL https://testing.es.data61.xyz ). So to run the tutorials, you can either:

 - use the tutorials from the `master` branch of this repository which will work with the currently deployed testing service,
 - or build and deploy the service from the same branch as the tutorials you would like to run, providing its URL to
   the tutorials via the environment variable `SERVER` (e.g. `SERVER=http://0.0.0.0:8851` if deployed locally).

Other use-cases are not supported and may fail for non-obvious reasons.

External Tutorials
------------------

The ``clkhash`` library includes a tutorial of carrying out record linkage on perturbed data.
<http://clkhash.readthedocs.io/en/latest/tutorial_cli.html>

