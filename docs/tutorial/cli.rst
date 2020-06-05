Command line example
--------------------

This brief example shows using ``anonlink`` - the command line tool that is packaged with the
``anonlink-client`` library. It is not a requirement to use ``anonlink-client`` with the Entity Service REST API.

We assume you have access to a command line prompt with Python and Pip installed.

Install ``anonlink-client``::

    $ pip install anonlink-client


Generate and split some mock personally identifiable data::

    $ anonlink generate 2000 raw_pii_2k.csv

    $ head -n 1 raw_pii_2k.csv > alice.txt
    $ tail -n 1500 raw_pii_2k.csv >> alice.txt
    $ head -n 1000 raw_pii_2k.csv > bob.txt


A corresponding hashing schema can be generated as well::

    $ anonlink generate-default-schema schema.json


Process the personally identifying data into :ref:`cryptographic-longterm-keys`::

    $ anonlink hash alice.txt horse_staple schema.json alice-hashed.json
    generating CLKs: 100%|████████████████████████████████████████████| 1.50K/1.50K [00:00<00:00, 6.69Kclk/s, mean=522, std=34.4]
    CLK data written to alice-hashed.json

    $ anonlink hash bob.txt horse_staple schema.json bob-hashed.json
    generating CLKs: 100%|████████████████████████████████████████████| 999/999 [00:00<00:00, 5.14Kclk/s, mean=520, std=34.2]
    CLK data written to bob-hashed.json


Now to interact with an Entity Service. First check that the service is healthy and responds to
a status check::

    $ anonlink status --server https://anonlink.easd.data61.xyz
    {"rate": 53129, "status": "ok", "project_count": 1410}

Then create a new linkage project and set the output type (to ``groups``)::

    $ anonlink create-project \
        --server https://anonlink.easd.data61.xyz \
        --type groups \
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

    $ anonlink upload --server https://anonlink.easd.data61.xyz \
                    --apikey 21d4c9249e1c70ac30f9ce03893983c493d7e90574980e55 \
                    --project 809b12c7e141837c3a15be758b016d5a7826d90574f36e74 \
                    alice-hashed.json
    {"receipt_token": "05ac237462d86bc3e2232ae3db71d9ae1b9e99afe840ee5a", "message": "Updated"}

    $ clkutil upload --server https://anonlink.easd.data61.xyz \
                    --apikey 3ad6ae9028c09fcbc7fbca36d19743294bfaf215f1464905 \
                    --project 809b12c7e141837c3a15be758b016d5a7826d90574f36e74 \
                    bob-hashed.json
    {"receipt_token": "6d9a0ee7fc3a66e16805738097761d38c62ea01a8c6adf39", "message": "Updated"}

Now we can compute linkages using various thresholds. For example to only see relationships where the
similarity is above ``0.9``::

    $ anonlink create --server https://anonlink.easd.data61.xyz \
                     --apikey 230a303b05dfd186be87fa65bf7b0970fb786497834910d1 \
                     --project 809b12c7e141837c3a15be758b016d5a7826d90574f36e74 \
                     --name "Tutorial mapping run" \
                     --threshold 0.9
    {"run_id": "31a6d3c775151a877dcac625b4b91a6659317046ea45ad11", "notes": "Run created by anonlink-client 0.1.2", "name": "Tutorial mapping run", "threshold": 0.9}


After a small delay the linkage result will have been computed and we can use ``anonlink`` to retrieve it::

    $ anonlink results --server https://anonlink.easd.data61.xyz \
                    --apikey  230a303b05dfd186be87fa65bf7b0970fb786497834910d1 \
                    --project 809b12c7e141837c3a15be758b016d5a7826d90574f36e74 \
                    --run 31a6d3c775151a877dcac625b4b91a6659317046ea45ad11
    State: completed
    Stage (3/3): compute output
    Downloading result
    Received result
    {
      "groups": [
        [
            [0, 403],
            [1, 903]
        ],
        [
            [0, 402],
            [1, 092]
        ],
        [
            [0, 401],
            [1, 901]
        ],
        ...

This output shows the linked pairs between Alice and Bob that have a similarity above 0.9.

Looking at the corresponding entities in Alice's data::

    head -n 405 alice.txt | tail -n 3
    901,Sandra Boone,1974/10/30,F
    902,Lucas Hernandez,1937/06/11,M
    903,Ellis Stevens,2008/06/02,M

And the corresponding entities in Bob's data::

    head -n 905 bob.txt | tail -n 3
    901,Sandra Boone,1974/10/30,F
    902,Lucas Hernandez,1937/06/11,M
    903,Ellis Stevens,2008/06/02,M