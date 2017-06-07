API
===

Open API Specification
----------------------

Note there is also an Open API specification for the service, in any cases
where this document is found to disagree with the spec - the spec is considered
the source of truth.

`Open API Specification <./_static/swagger.yaml>`__

v1 REST API
-----------

-  All parameters and returned objects are JSON with content-type set to
   ``application/json``.
-  All authentication tokens are 48 character hex strings.
-  The resource identifiers are also 48 char hex strings.
-  HTTP status codes are used to distinguish server outcomes.
-  All endpoints are prefixed with ``/api/v1``


``/status`` (GET)
~~~~~~~~~~~~~~~~~

System health endpoint. Suitable for using as load balancer health
check. Checks that redis cache and database are operational.

**200** Provides system wide comparison rate, and the number of mappings
in the database.

::

    {
        'status': 'ok',
        'number_mappings': 12, 'rate': 150000000
    }

**5XX** System is experiencing difficulties. E.g. application can't
connect to database.

``/version`` (GET)
~~~~~~~~~~~~~~~~~~

**200** Returns a JSON object with versions of used libraries.

::

    {
        "anonlink": "0.4.1",
        "entityservice": "v1.3.0",
        "libc": "glibc2.2.5",
        "python": "3.5.2"
    }

``/mappings/`` (GET)
~~~~~~~~~~~~~~~~~~~~

List of all mappings with their completion status.

**200** Data is returned with a ``mappings`` array of objects:

::

    {
        "mappings": [
            {
                'resource_id': '4e10f79e899cbdeb1b2999730c19279ffd62e2895fcd3d39',
                'ready': True,
                'time_added': '2016-05-10T07:12:13.501194',
                'time_completed': '2016-05-10T07:12:16.300494'
            }, ...
        ]
    }

-  ``'time_added'`` and ``'time_completed'`` are represented in `ISO
   8601
   format <https://docs.python.org/3/library/datetime.html#datetime.datetime.isoformat>`__.
   ``'time_completed'`` will be null if the matching hasn't yet
   completed.
-  ``ready`` indicates if the entity matching has been completed

``/mappings`` (POST)
~~~~~~~~~~~~~~~~~~~~

Create and configure a new entity matching task.

Prepare resources and endpoints to accept updates from data providers.
Provides the caller with credentials that will be required when adding
data to the mapping and accessing the results.

Parameters
^^^^^^^^^^

-  ``result_type`` specifies what information is available after the
   entity resolving process has completed. The options are:

   -  ``"permutation"`` - Create a random permutation and Paillier
      encrypted mask.
   -  ``"mapping"`` - Directly output a lookup table of
      ``indexA = indexB``
   -  ``"permutation_unencrypted_mask"`` - Create a random permutation
      and an unencrypted mask.

-  ``public_key`` A Paillier public key serialized as the `JWK
   format <https://python-paillier.readthedocs.io/en/develop/serialisation.html#jwk-serialisation>`__.
   with an ``n`` attribute. Only required if
   ``result_type = "permutation"``.

-  ``paillier_context`` A Paillier context serialized with a ``base``
   and ``encoded`` attribute. Only required if
   ``result_type = "permutation"``. Example: {% code lang=json
   linenumbers=false %} { "encoded": true, "base": 2 } {% endcode %}

-  ``schema`` details which have been determined and agreed on by each
   party. Although these comprise the column names, the raw data will
   never be sent to this entity service. The ``schema`` is an array of
   feature description objects. Feature descriptions must have
   ``identifier``, ``weight`` and ``notes`` attributes. Each participant
   will be able to see the schema to verify it is what they expect.

   **Example**::

       [
           {"identifier": "NAME freetext", "weight": 1, "notes":""},
           {"identifier": "DOB YYYY/MM/DD", "weight": 1, "notes":""}
       ]

    See `Identifier Types <#identifier-types>`__ for all valid
    ``identifiers``.

Returns
^^^^^^^

A JSON object with the following attributes:

-  ``'resource_id'`` - resource identifier to use for this mapping.
-  ``'update_tokens'`` - an array of **single use tokens** required to
   provide ``CLK`` data.
-  ``'result_token'`` - a token required to access **mapping** results
   if the ``result_type`` is ``"mapping"`` of to access the
   **unencrypted mask** result if the ``result_type`` is
   ``permutation_unencrypted_mask``.

**Example**::

    {
        'resource_id': 'c8a1251e39f30c9feff5e67ba9c35cb0a3e2fd9edb6fe63a',
        'result_token': 'f58d2b097f76bc9ae8b51646465b5dd2d4f005c41477380e',
        'update_tokens': [
            '1f398668ffc0dbe3f98f8d36c62cc2b2c868f76cf6e7cf38',
            '39ffb4bb63b9f75a25092a2f3f640c43fe50a34eaedcfc94'
        ]
    }

``/api/v1/mappings/<mapping-id>`` (GET)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Designed to be called **after** all data providers have called update at
least once, otherwise a 503 will be returned.

Header
^^^^^^

``token`` required to authenticate the caller. The source of the token
depends on the mapping's ``result_type``.

-  if the ``result_type`` is ``"mapping"`` then ``token`` is provided
   when initially creating the mapping (as ``result-token``).
-  if the ``result_type`` is ``"permutation"`` then ``token`` is
   obtained when organisations add data to the mapping (as
   ``receipt-token``)
-  if the ``result_type`` is ``permutation_unenecrypted_mask``, the
   ``token`` to access the mask is provided initially creating the
   mapping (as ``result-token``), and the ``token`` to access the
   permutation is obtained when organisations add data to the mapping
   (as ``receipt-token``)

Returns
^^^^^^^

The response body for completed matchings depends on the mappings's
``result_type``.

Returns when result\_type = "mapping":
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**200** The mapping of indices between parties. Data is returned as
``json`` object e.g.,::

    { "mapping":
        {
            "0": "5",
            "2": "0"
        }
    }


Returns when result\_type = "permutation":
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**200** The permutation, and mask specific for the calling organisation.
Data is returned as ``json`` object e.g,::

    {
        "permutation: [3,0,4,1,2],
        "mask": [0,1,0,1,1], <-- As paillier encrypted, base64 encoded numbers
        "paillier_context": { "base": 2, "encoded": true }
    }

In this example the first three elements in the original dataset are
included, but have been reordered to the second, fourth and fifth
positions. The other elements have been excluded with the encrypted
mask. Note the permutation is specific to the caller. Also any data
after row 5 is to be discarded after the reordering has been applied.

The ``mask`` is a json array of Paillier encrypted numbers. These are
the ciphertexts as integer strings. The encoded number base is ``2``,
and the precision is set to ``1e3``. The exponent is not serialized, as
it will always be 0. The resulting ciphertext is serialized with base64
encoding.

In Python using ``python-paillier``:
``int_to_base64(public_key.encrypt(enc, precision).ciphertext())``

Returns when result\_type = "permutation\_unencrypted\_mask":
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The data providers will receive for the permutation::

    {
        "permutation": [3,0,4,1,2],
        "rows": 5
    }

E.g. for the mask::

    { "mask": [0,1,0,1,1] }

The mask is an array of 0/1 numbers.

Error cases are also JSON, and all have a ``message`` attribute

**400** If information provided is invalid. E.g. no ``schema``, invalid
``result_type``, missing or invalid public key.

**401** If auth token missing

**403** If the token is not valid.

**404** If the mapping doesn't exist

**503** If the mapping isn't yet ready. This will include an indication
of the current progress::

    {
        "message": "Mapping isn't yet ready",
        "elapsed": 124.73,
        "total": 100200030,
        "current": 200000,
        "progress": 200000/100200030
    }

``/api/v1/mappings/<mapping-id>`` (PUT)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Called by each of the data providers with their calculated ``CLK``
vectors. The mapping must have been created, and the caller must have
both the ``mapping-id`` and ``token`` in order to contribute data.

When the second party successfully adds data the matching task is
queued; although it is worth noting there is no indication to the caller
that this has occurred.

Parameters
^^^^^^^^^^

-  ``token`` - A single use **update** token as provided when creating
   the mapping.
-  ``clks`` - Array of this party's Bloom Filters. One per entity/row.
   Format specified `below <#bloom-filter-format>`__.

Note maximum request size is currently set to ``~10 GB``, which
**should** translate to over ten million entities.

Returns
^^^^^^^

-  **201** In the successful case a json body with a ``message`` and a
   data receipt ``receipt-token``. If the mapping's ``result_type`` is
   ``"permutation"`` or ``"permutation_unencrypted_mask"`` then this
   ``receipt-token`` is required to retrieve the permutation for this
   organisation (with the encrypted mask or without mask).

   ::

    {
        "message": "Updated",
        "receipt-token": "97ec447cb078b70fe3bced7db51585a7eb1265ac7fab2992"
    }

-  **400** If required information is not provided, or wrong format.
-  **401** If the authentication token in not provided.
-  **403** IF the authentication token is not valid.

``/api/v1/mappings/<mapping-id>`` (DELETE)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Removes the given mapping.

-  **204** with no data if the mapping was deleted.
-  **404** If the mapping was not found.

``/api/v1/danger/generate-names`` (GET)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Generates sample PII data with given overlap.

Parameters:

-  *n* is the number of entities each org should have.
-  *p* is the proportion in common

Returns a json object with an ``A`` and ``B`` array.
