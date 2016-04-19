import os
import json
from anonlink import randomnames, entitymatch

from serialization import *


def create_test_data(entities, crossover=0.8, save_raw=True):
    """
    Uses the NameList data and schema and creates
    local files for raw data and clk data:

    - e1_NUM_raw.csv
    - e1_NUM.json
    - e2_NUM_raw.csv
    - e2_NUM.json

    :param bool save_raw: Set to False to skip saving raw files
    """
    print("Generating random test data for {} individuals".format(entities))

    from timeit import default_timer as timer

    t0 = timer()

    nl = randomnames.NameList(entities * 2)
    s1, s2 = nl.generate_subsets(entities, crossover)
    t1 = timer()
    print("generated data in {:.3f} s".format(t1-t0))

    def save_subset_data(s, f):
        print(",".join(nl.schema), file=f)
        for entity in s:
            print(",".join(map(str, entity)), file=f)

    def save_filter_data(filters, f):
        print("Serializing filters")
        serialized_filters = serialize_filters(filters)

        json.dump(serialized_filters, f)


    keys = ('something', 'secret')

    if save_raw:
        with open("data/e1_{}_raw.csv".format(entities), "w") as f:
            save_subset_data(s1, f)

        with open("data/e2_{}_raw.csv".format(entities), "w") as f:
            save_subset_data(s2, f)
    t2 = timer()
    print("Saved raw data in {:.3f} s".format(t2-t1))
    print("Locally hashing identity data to create bloom filters")

    # Save serialized filters
    with open("data/e1_{}.json".format(entities), 'w') as f1:
        save_filter_data(entitymatch.calculate_bloom_filters(s1, nl.schema, keys), f1)

    with open("data/e2_{}.json".format(entities), 'w') as f2:
        save_filter_data(entitymatch.calculate_bloom_filters(s2, nl.schema, keys), f2)

    t3 = timer()
    print("Hashed and serialized data in {:.3f} s".format(t3-t2))


if __name__ == "__main__":
    size = int(os.environ.get("ENTITY_SERVICE_TEST_SIZE", "100"))
    create_test_data(size)
