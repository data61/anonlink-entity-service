Security
========


The service isn't given any personally identifying information in raw form - rather clients must
locally compute a :abbr:`CLK (Cryptographic Longterm Key)` which is a hashed version of the data to
be linked. The standard output of the Entity Service is a mapping between row indices in
set A to row indices in set B. This output is only available to the client who created the mapping,
but it is worth highlighting that it does (by design) leak information about the intersection of the
two sets of entities.

The :abbr:`CLK (Cryptographic Longterm Key)` is computed and compared following the method described
by Rainer Schnell, Tobias Bachteler, and Jörg Reiher in `A Novel Error-Tolerant Anonymous Linking Code`_.
We have deviated from their approach by using a :abbr:`KDF (Key derivation function)` to ensure the
hash functions are independent. See the detailed discussion in
`Who Is 1011011111…1110110010? Automated Cryptanalysis of Bloom Filter Encryptions of Databases with Several Personal Identifiers <https://link.springer.com/chapter/10.1007/978-3-319-27707-3_21/fulltext.html>`_
where Kroll and Steinmetzer present cryptanalysis and an attack on Bloom filters built from multiple
identifiers.

The semantic security of the CLKs depends on two factors:

1) Multiple features are hashed to create the CLK. If just one or two features (e.g. name) are used,
   population statistics on the distribution of names can be used to identify records based solely on
   the CLKs. See the paper `Cryptanalysis of Basic Bloom Filters Used for Privacy Preserving Record Linkage`_
   for an indepth analysis.
2) The `HMAC <https://en.wikipedia.org/wiki/Hash-based_message_authentication_code>`_ secret that the
   entity providing organizations share is unique (not reused between mappings) and is kept secret
   from the Linkage Service.


Attack Vectors
--------------


**Recovery from the distance measurements**
One of the output types includes the plaintext distance measurements between entities, this additional
information can be used to fingerprint individual entities based on their ordered similarity scores.
In combination with public information this can lead to recovery of identity. This attack is described
in section 3 of
`Vulnerabilities in the use of similarity tables in combination with pseudonymisation to preserve data privacy in the UK Office for National Statistics' Privacy-Preserving Record Linkage`_
by Chris Culnane, Benjamin I. P. Rubinstein, Vanessa Teague.
In order to prevent this attack it is important not to provide the similarity table to untrusted
parties.


**Stealing/Leaking mapping result**
The resulting mapping linkages could be leaked to another party - potentially knowing the overlap
between the organizations is revealing. This is prevented by using unique authorization codes generated
for each mapping which is required to retrieve the results.

**Stealing/Leaking uploaded CLKs**

The uploaded CLKS for one organization could be leaked to the partner organization - who possesses the
HMAC secret breaking semantic security. The entity service doesn't expose an API that allows users
to access any CLKS, the object store (MINIO or S3) and the database (postgresql) are configured to
not allow public access.


Possible Weaknesses
-------------------

When creating the bi-grams, the first and last bi-gram are padded with a whitespace. This is a
weakness, because it allows an attacker more easily to find the beginning and the end of a word.
Need to investigate if dropping the padding decreases matching accuracy.

.. _A Novel Error-Tolerant Anonymous Linking Code: http://www.record-linkage.de/-download=wp-grlc-2011-02.pdf

.. _Cryptanalysis of Basic Bloom Filters Used for Privacy Preserving Record Linkage: http://repository.cmu.edu/cgi/viewcontent.cgi?article=1121

.. _Vulnerabilities in the use of similarity tables in combination with pseudonymisation to preserve data privacy in the UK Office for National Statistics' Privacy-Preserving Record Linkage: https://arxiv.org/abs/1712.00871

