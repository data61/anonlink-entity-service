
.. _changelog:

Changelog
=========

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
 

