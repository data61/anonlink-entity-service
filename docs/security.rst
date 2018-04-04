.. _security:

Security
========

The service isn't given any personally identifying information in raw form - rather clients must
locally compute a :abbr:`CLK (Cryptographic Longterm Key)` which is a hashed version of the data to
be linked.

Considerations for each output type
-----------------------------------

Direct Mapping Table
~~~~~~~~~~~~~~~~~~~~

The default output of the Entity Service comprises a list of edges - connections between rows in
dataset A to rows in dataset B. This assumes at most a 1-1 corrospondence - each entity will
only be present in zero or one edge.

This output is only available to the client who created the mapping,
but it is worth highlighting that it does (by design) leak information about the intersection of the
two sets of entities.

**Knowledge about set intersection**
This output contains information about which particular entities are shared, and which are not.
Potentially knowing the overlap between the organizations is disclosive. This is mitigated by
using unique authorization codes generated for each mapping which is required to retrieve the
results.

**Row indicies exposed**
The output directly exposes the row indices provided to the service, which if not randomized may be
disclosive. For example entities simply exported from a database might be ordered by age, patient
admittance date, salary band etc.


Similarity Score
~~~~~~~~~~~~~~~~

All calculated similarities (above a given threshold) between entities are returned. This
output comprises a list of weighted edges - similarity between rows in dataset A to rows
in dataset B. This is a many to many relationship where entities can appear in multiple edges.

**Recovery from the distance measurements**
This output type includes the plaintext distance measurements between entities, this additional
information can be used to fingerprint individual entities based on their ordered similarity scores.
In combination with public information this can lead to recovery of identity. This attack is described
in section 3 of
`Vulnerabilities in the use of similarity tables in combination with pseudonymisation to preserve data privacy in the UK Office for National Statistics' Privacy-Preserving Record Linkage`_
by Chris Culnane, Benjamin I. P. Rubinstein, Vanessa Teague.

In order to prevent this attack it is important not to provide the similarity table to untrusted
parties.


Permutation and Mask
~~~~~~~~~~~~~~~~~~~~

This output type involves creating a random reordering of the entities for both
organizations; and creating a binary mask vector revealing where the reordered
rows line up. This output is designed for use in multi-party computation algorithms.

This mitigates the **Knowledge about set intersection** problem from the direct
mapping output - assuming the mask is not made available to the data providers.

Note the mask will be the length of the smaller data set and is applied after permuting
the entities. This means the owner of the larger data set learns a subset of her rows
which are not in the smaller data set.

Permutation and Encrypted Mask
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Similar to **Permutation and Mask**, except the mask is encrypted using
a Paillier Public Key given when creating the mapping. The mask is
provided along with the unenencrypted permutation to each organization
with a valid ``receipt-token``.


.. _auth:

Authentication / Authorization
------------------------------

The entity service does not support authentication, yet. This is planned for a future version.

All sensitive data is protected by token-based authorization. That is, you need to provide the correct token to access
different resources. A token is a unique random 192 bit string.

There are three different types of tokens:

- *update-token*: required to upload a party's CLKs.
- *result_token*: required to access the result of the entity resolution process. This is, depending on the
  :ref:`output type <result-types>`, either similarity scores, a direct mapping table, or a mask.
- *receipt_token*: this token is returned to either party after uploading their respective CLKs. With this
  *receipt-token* they can then access their respective permutations, if the output type of the mapping is set to
  permutation and (encrypted) mask.

.. important::
   These tokens are the only artifacts that protect the sensitive data. Therefore it is paramount to make sure that only
   authorized parties have access to these tokens!


Attack Vectors
--------------

The following attack vectors need to be considered for all output types.

**Stealing/Leaking uploaded CLKs**

The uploaded CLKs for one organization could be leaked to the partner organization - who possesses the
HMAC secret breaking semantic security. The entity service doesn't expose an API that allows users
to access any CLKs, the object store (MINIO or S3) and the database (postgresql) are configured to
not allow public access.

.. _Vulnerabilities in the use of similarity tables in combination with pseudonymisation to preserve data privacy in the UK Office for National Statistics' Privacy-Preserving Record Linkage: https://arxiv.org/abs/1712.00871

