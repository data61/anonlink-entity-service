Tutorials
=========

.. toctree::
   :maxdepth: 1

   Permutations.ipynb
   Similarity Scores.ipynb


External Tutorials
------------------

The ``clkhash`` library includes a tutorial of carrying out record linkage on perturbed data.
<http://clkhash.readthedocs.io/en/latest/tutorial_cli.html>

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


A corresponding hashing schema can be generated as well::

    $ clkutil generate-default-schema schema.json


Process the personally identifying data into :ref:`cryptographic-longterm-keys`::

    $ clkutil hash alice.txt horse staple schema.json alice-hashed.json
    generating CLKs: 100%|████████████████████████████████████████████| 1.50K/1.50K [00:00<00:00, 6.69Kclk/s, mean=522, std=34.4]
    CLK data written to alice-hashed.json

    $ clkutil hash bob.txt horse staple schema.json bob-hashed.json
    generating CLKs: 100%|████████████████████████████████████████████| 999/999 [00:00<00:00, 5.14Kclk/s, mean=520, std=34.2]
    CLK data written to bob-hashed.json


Now to interact with an Entity Service. First check that the service is healthy and responds to
a status check::

    $ clkutil status --server https://testing.es.data61.xyz
    {"rate": 53129, "status": "ok", "project_count": 1410}

Then create a new linkage project and set the output type (to ``mapping``)::

    $ clkutil create-project \
        --server https://testing.es.data61.xyz \
        --type mapping \
        --schema schema.json \
        --output credentials.json

The entity service replies with a project id and credentials which get saved into the file ``credentials.json``.
The contents is two upload tokens and a result token::

    {
        "update_tokens": [
            "21d4c9249e1c70ac30f9ce03893983c493d7e90574980e55",
            "3ad6ae9028c09fcbc7fbca36d19743294bfaf215f1464905"
        ],
        "project_id": "809b12c7e141837c3a15be758b016d5a7826d90574f36e74",
        "result_token": "230a303b05dfd186be87fa65bf7b0970fb786497834910d1"
    }

These credentials get substituted in the following commands. Each CLK dataset
gets uploaded to the Entity Service::

    $ clkutil upload --server https://testing.es.data61.xyz \
                    --apikey 21d4c9249e1c70ac30f9ce03893983c493d7e90574980e55 \
                    --project 809b12c7e141837c3a15be758b016d5a7826d90574f36e74 \
                    alice-hashed.json
    {"receipt_token": "05ac237462d86bc3e2232ae3db71d9ae1b9e99afe840ee5a", "message": "Updated"}

    $ clkutil upload --server https://testing.es.data61.xyz \
                    --apikey 3ad6ae9028c09fcbc7fbca36d19743294bfaf215f1464905 \
                    --project 809b12c7e141837c3a15be758b016d5a7826d90574f36e74 \
                    bob-hashed.json
    {"receipt_token": "6d9a0ee7fc3a66e16805738097761d38c62ea01a8c6adf39", "message": "Updated"}

Now we can compute mappings using various thresholds. For example to only see relationships where the
similarity is above ``0.9``::

    $ clkutil create --server https://testing.es.data61.xyz \
                     --apikey 230a303b05dfd186be87fa65bf7b0970fb786497834910d1 \
                     --project 809b12c7e141837c3a15be758b016d5a7826d90574f36e74 \
                     --name "Tutorial mapping run" \
                     --threshold 0.9
    {"run_id": "31a6d3c775151a877dcac625b4b91a6659317046ea45ad11", "notes": "Run created by clkhash 0.11.2", "name": "Tutorial mapping run", "threshold": 0.9}


After a small delay the mapping will have been computed and we can use ``clkutil`` to retrieve the
results::

    $ clkutil results --server https://testing.es.data61.xyz \
                    --apikey  230a303b05dfd186be87fa65bf7b0970fb786497834910d1 \
                    --project 809b12c7e141837c3a15be758b016d5a7826d90574f36e74 \
                    --run 31a6d3c775151a877dcac625b4b91a6659317046ea45ad11
    State: completed
    Stage (3/3): compute output
    Downloading result
    Received result
    {
      "mapping": {
        "0": "500",
        "1": "501",
        "10": "510",
        "100": "600",
        "101": "601",
        "102": "602",
        "103": "603",
        "104": "604",
        "105": "605",
        "106": "606",
        "107": "607",
        ...

This mapping output is telling us that the similarity is above our threshold between identified rows
of Alice and Bob's data sets.

Looking at the first two entities in Alice's data::

    head alice.txt -n 3
    INDEX,NAME freetext,DOB YYYY/MM/DD,GENDER M or F
    500,Arjun Efron,1990/01/14,M
    501,Sedrick Verlinden,1954/11/28,M

And looking at the corresponding 500th and 501st entities in Bob's data::

    tail -n 499 bob.txt | head -n 2
    500,Arjun Efron,1990/01/14,M
    501,Sedrick Verlinden,1954/11/28,M
