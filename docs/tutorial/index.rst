Tutorials
=========

.. toctree::

   Unencrypted Masked Matchmaking - All in one.ipynb
   Matchmaking - Expose Sparse Similarity Scores.ipynb


Command line example
--------------------


This example can be carried out if you have docker installed. Note you can change the `--server`
address to talk to a particular deploymed entity service.::

    docker run -it python bash
    pip install clkhash

    clkutil generate 2000 raw_pii_2k.csv

    head -n 1 raw_pii_2k.csv > alice.txt
    tail -n 1500 raw_pii_2k.csv >> alice.txt
    head -n 1000 raw_pii_2k.csv > bob.txt

    clkutil hash alice.txt horse staple alice-hashed.json
    clkutil hash bob.txt horse staple bob-hashed.json


Now to interact with an Entity Service::

    clkutil create --server https://es.data61.xyz --type mapping --threshold 0.9 --output credentialss.json

The entity service replies with a mapping id and credentials - two upload tokens and a result token. These get substituted
in the following commands::

    clkutil upload --server https://es.data61.xyz --apikey 80d292edab3f40465145fdbac0a67e0850dd180a63c6d1b0 --mapping 03180c847c72baf654141b7f7ee4ca2f255a8dc3bc401df1 alice-hashed.json
    clkutil upload --server https://es.data61.xyz --apikey b27377f912b5c8f43be8dd516cc695f52f8628c820291181 --mapping 03180c847c72baf654141b7f7ee4ca2f255a8dc3bc401df1 bob-hashed.json

    clkutil results --server https://es.data61.xyz --apikey 4653802ad2e576492368f1b923e0df3bb3225e326b5b4588 --mapping 03180c847c72baf654141b7f7ee4ca2f255a8dc3bc401df1

