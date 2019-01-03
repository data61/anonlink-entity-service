Deployment Risks
================

The purpose of this document is to record known deployment risks of the entity service and our mitigations.
References the 2017 Top 10 security risks - https://www.owasp.org/index.php/Top_10-2017_Top_10


Risks
-----

User accesses unit record data
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A1 - Injection

A3 - Sensitive Data Exposure

Unauthorized user accesses results
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A6 - Security misconfiguration.

A2 - Broken authentication.

A5 - Broken access control.


Authorized user attacks the system
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A10 - Insufficient Logging & Monitoring
A3 - Sensitive Data Exposure

An admin can access the raw clks uploaded by both parties.

However a standard user cannot.

User coerces N1 to execute attacking code
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Insecure deserialization.
Compromised shared host.

An underlying component has a vulnerability
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Dependencies including anonlink could have vulnerabilities.

