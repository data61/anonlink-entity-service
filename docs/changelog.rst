
.. _changelog:

Changelog
=========

Version 1.7.3 (2018-03-16)
--------------------------

Deployment and documentation sprint.

- Fixes a bug where only the top `k` results of a chunk were being requested from anonlink. #59 #84
- Updates to helm deployment templates to support a single namespace having multiple entityservices. Helm
  charts are more standard, some config has moved into a configmap and an experimental cert-manager
  configuration option has been added. #83, #90
- More sensible logging during testing.
- Every http request now has a (globally configurable) timeout
- Minor update regarding handling uploading empty clks. #92
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
 
