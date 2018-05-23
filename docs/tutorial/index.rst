Tutorials
=========

.. toctree::
   :maxdepth: 1

   Tutorial 01 - Mapping.ipynb
   Tutorial 02 - Permutations.ipynb
   Tutorial 03 - Similarity Scores.ipynb


Command line example
--------------------

This brief example shows using ``clkutil`` - the command line tool that is packaged with the
``clkhash`` library. It is not a requirement to use ``clkhash`` with the Entity Service REST API.

We assume you have access to a command line prompt with Python and Pip installed.

Install ``clkhash``::

    $ pip install clkhash


Generate and split some mock personally identifiable data::

    $ clkutil generate 2000 raw_pii_2k.csv

    $ head -n 1 raw_pii_2k.csv > alice.txt
    $ tail -n 1500 raw_pii_2k.csv >> alice.txt
    $ head -n 1000 raw_pii_2k.csv > bob.txt


Process the personally identifying data into :ref:`cryptographic-longterm-keys`::

    $ clkutil hash alice.txt horse staple alice-hashed.json
    generating CLKs: 100%|████████████████████████████████████████████| 1.50K/1.50K [00:00<00:00, 6.69Kclk/s, mean=522, std=34.4]
    CLK data written to alice-hashed.json

    $ clkutil hash bob.txt horse staple bob-hashed.json
    generating CLKs: 100%|████████████████████████████████████████████| 999/999 [00:00<00:00, 5.14Kclk/s, mean=520, std=34.2]
    CLK data written to bob-hashed.json


Now to interact with an Entity Service - we start by creating a linkage project and setting the
output type (to ``mapping``) and the threshold (to ``0.9``)::

    $ clkutil create --server https://es.data61.xyz \
                     --type mapping \
                     --threshold 0.9 \
                     --output credentials.json
    Entity Matching Server: https://es.data61.xyz
    Checking server status
    Server Status: ok
    Schema: NOT PROVIDED
    Type: mapping
    Creating new mapping
    Mapping created

The entity service replies with a mapping id and credentials which get saved into the file ``credentials.json``.
The contents is two upload tokens and a result token::

    {
        "resource_id": "fc906aee6a642988a40e2605ab6c8d71be2434d2faa744c7",
        "result_token": "7c6101a836b6d5f74746dcf231c87967daa9e7d8297d3cd3",
        "update_tokens": [
            "daa9b963ee293a5977daf4f5a64888266f99b92de9ce1bb2",
            "faa90a1bcdfed863dfff5696ce4652b36ff71193ba0fd502"
        ]
    }

These credentials get substituted in the following commands. Each CLK dataset
gets uploaded to the Entity Service::

    $ clkutil upload --server https://es.data61.xyz \
                    --apikey daa9b963ee293a5977daf4f5a64888266f99b92de9ce1bb2 \
                    --mapping fc906aee6a642988a40e2605ab6c8d71be2434d2faa744c7 \
                    alice-hashed.json
    Uploading CLK data from alice-hashed.json
    To Entity Matching Server: https://es.data61.xyz
    Mapping ID: fc906aee6a642988a40e2605ab6c8d71be2434d2faa744c7
    Checking server status
    Status: ok
    Uploading CLK data to the server
    {"message": "Updated", "receipt-token": "991b6ef7b2a8c0d552a38bed54ca8637e8f5615a096064c8"}

    $ clkutil upload --server https://es.data61.xyz \
                    --apikey faa90a1bcdfed863dfff5696ce4652b36ff71193ba0fd502 \
                    --mapping fc906aee6a642988a40e2605ab6c8d71be2434d2faa744c7 \
                    bob-hashed.json
    Uploading CLK data from bob-hashed.json
    To Entity Matching Server: https://es.data61.xyz
    Mapping ID: fc906aee6a642988a40e2605ab6c8d71be2434d2faa744c7
    Checking server status
    Status: ok
    Uploading CLK data to the server
    {"message": "Updated", "receipt-token": "341adda46002ee7751bcb852c04f6d6c1611d6ad383791b1"}


After a small delay the mapping will have been computed and we can use ``clkutil`` to retrieve the
results::

    $ clkutil results --server https://es.data61.xyz \
                    --apikey 7c6101a836b6d5f74746dcf231c87967daa9e7d8297d3cd3 \
                    --mapping fc906aee6a642988a40e2605ab6c8d71be2434d2faa744c7
    Checking server status
    Status: ok
    Response code: 200
    Received result
    {"mapping": {"500": "0", "501": "1", "502": "2", "503": "3", "504": "4", ...}}

This mapping output is telling us that the similarity is above our threshold between the 501st row
of Alice's data set and the first row of Bob's.