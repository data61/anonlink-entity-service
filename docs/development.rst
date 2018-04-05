Development
===========

.. toctree::
   :maxdepth: 1

   changelog
   future

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
   celery backend.

Each of these has been packaged as a docker image, however the use of an
external postgres database can be configured through environment
variables. Multiple workers can be used to distribute the work beyond
one machine - by default all cores will be used for computing similarity
scores and encrypting the mask vector.


