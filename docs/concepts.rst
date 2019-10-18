Concepts
========

.. _cryptographic-longterm-keys:

Cryptographic Longterm Key
---------------------------

A Cryptographic Longterm Key is the name given to a
`Bloom filter <https://en.wikipedia.org/wiki/Bloom_filter>`_ used as a privacy
preserving representation of an entity. Unlike a cryptographic hash function, a CLK preserves
similarity - meaning two similar entities will have similar CLKs. This property is necessary
for probabilistic record linkage.

:abbr:`CLK (Cryptographic Longterm Key)`\ s are created independent of the entity service following
a *keyed hashing* process.

A CLK incorporates information from multiple identifying fields (e.g., name, date of birth, phone number)
for each entity. The :ref:`schema <schema>` section details how to capture the configuration for
creating CLKs from PII, and the :ref:`next <bloom-filter-format>` section outlines how to serialize
CLKs for use with this service's `api <./api.html>`_.

.. note::

   The Cryptographic Longterm Key was introduced in
   `A Novel Error-Tolerant Anonymous Linking Code
   <http://www.record-linkage.de/-download=wp-grlc-2011-02.pdf>`__ by
   Rainer Schnell, Tobias Bachteler, and Jörg Reiher.


.. _bloom-filter-format:

Bloom Filter Format
-------------------

A Bloom filter is simply an encoding of PII as a `bitarray`.

This can easily be represented as bytes (each being an 8 bit number between 0 and 255).
We serialize by `base64` encoding the raw bytes of the bit array.

An example with a 64 bit filter::

    # bloom filters binary value
    '0100110111010000101111011111011111011000110010101010010010100110'

    # which corresponds to the following bytes
    [77, 208, 189, 247, 216, 202, 164, 166]

    # which gets base64 encoded to
    'TdC999jKpKY=\n'



As with standard Base64 encodings, a newline is introduced every 76
characters.

.. _schema:

Schema
------

It is important that participating organisations agree on how personally identifiable information is
processed to create the :ref:`clks <cryptographic-longterm-keys>`. We call the configuration for creating CLKs
a *linkage schema*. The organisations have to agree on a schema to ensure their CLKs are
comparable.

The linkage schema is documented in `clkhash <http://clkhash.readthedocs.io/en/latest/schema.html>`_,
our reference implementation written in Python.

.. note::

    Due to the *one way nature* of hashing, the entity service can't determine
    whether the linkage schema was followed when clients generated CLKs.


.. _comparing-clks:

Comparing Cryptograhpic Longterm Keys
-------------------------------------

The similarity metric used is the
`Sørensen–Dice index <https://en.wikipedia.org/wiki/S%C3%B8rensen%E2%80%93Dice_coefficient>`_ -
although this may become a configurable option in the future.

.. _result-types:

Output Types
------------

The Entity Service supports different **result types** which effect what output is produced, and
who may see the output.

.. warning::

   **The security guarantees differ substantially for each output type.**
   See the :ref:`security` document for a treatment of these concerns.


Similarity Score
~~~~~~~~~~~~~~~~

Similarities scores are computed between all CLKs in each organisation - the scores above a given
threshold are returned. This output type is currently the only way to work with 1 to many
relationships.

The ``result_token`` (generated when creating the mapping) is required. The ``result_type`` should
be set to ``"similarity_scores"``.

Results are a simple JSON array of arrays::

   [
       [index_a, index_b, score],
       ...
   ]

Where the index values will be the 0 based row index from the uploaded CLKs, and
the score will be a Number between the provided threshold and ``1.0``.

A score of ``1.0`` means the CLKs were identical. Threshold values are usually between
``0.5`` and ``1.0``.

.. note::

    The maximum number of results returned is the product of the two data set lengths.

    For example:

        Comparing two data sets each containing 1 million records with a threshold
        of ``0.0`` will return 1 trillion results (``1e+12``).

Direct Mapping Table (Deprecated for Groups Result)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The direct mapping takes the similarity scores and simply assigns the highest scores as links.

The links are exposed as a lookup table using indices from the two organizations::

    {
        index_a: index_b,
        ...
    }


The ``result_token`` (generated when creating the mapping) is required to retrieve the results. The
``result_type`` should be set to ``"mapping"``.

Groups Result
~~~~~~~~~~~~~

The groups result has been created for multi-party linkage, and will replace the direct mapping result
for two parties as it contains the same information in a different format.

The result is a list of groups of records. Every record in such a group belongs to the same entity and
consists of two values, the party index and the row index::

    [
      [
        [party_id, row_index],
        ...
      ],
      ...
    ]


The ``result_token`` (generated when creating the mapping) is required to retrieve the results. The
``result_type`` should be set to ``"groups"``.

Permutation and Mask
~~~~~~~~~~~~~~~~~~~~

This protocol creates a random reordering for both organizations; and creates a mask revealing where
the reordered rows line up.

Accessing the mask requires the ``result_token``, and accessing the permutation requires a
``receipt-token`` (provided to each organization when they upload data).

Note the mask will be the length of the smaller data set and is applied after permuting the entities.
This means the owner of the larger data set learns a subset of her rows which are not in the smaller
data set.

The ``result_type`` should be set to ``"permutations"``.