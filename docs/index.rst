Entity Service - v\ |release|
=============================


.. toctree::
   :maxdepth: 2

   concepts
   security
   api
   deployment
   development


The *Entity Service* allows two organizations to carry out private record linkage. Matching records
without disclosing personally identifiable information.

Each party locally hash their entities' data (e.g. using
`clkhash <https://github.com/n1analytics/clkhash>`_)
generating :ref:`cryptographic-longterm-keys`. These ``clks`` are uploaded from both data providers
to this service. The service then calculates the similarity between entities. Depending on
configuration, the output is returned as :ref:`a mapping, a permutation and mask, or similarity scores <result-types>`.

This service relies on the internal Python library
`anonlink <https://github.csiro.au/magic/AnonymousLinking>`_
for computing entity similarity by comparing Cryptographic Longterm Keys
(``clks``).

.. figure:: _static/entity-overview.png
   :alt: Entity Service Overview
   :width: 600 px

