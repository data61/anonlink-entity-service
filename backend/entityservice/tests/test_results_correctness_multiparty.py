import pathlib
import pickle

import anonlink

from entityservice.serialization import binary_pack_filters
from entityservice.tests.util import (
    create_project_upload_data, delete_project, get_run_result, post_run)

DATA_FILENAME = 'test-multiparty-results-correctness-data.pkl'
DATA_PATH = pathlib.Path(__file__).parent / 'testdata' / DATA_FILENAME
DATA_HASH_SIZE = 128
THRESHOLD = .8


def test_groups_correctness(requests):
    # We assume that anonlink computes the right results.
    
    with open(DATA_PATH, 'rb') as f:
        # He's some filters I prepared earlier.
        filters = pickle.load(f)

    candidate_pairs = anonlink.candidate_generation.find_candidate_pairs(
        filters,
        anonlink.similarities.dice_coefficient_accelerated,
        THRESHOLD)
    true_groups = anonlink.solving.greedy_solve(candidate_pairs)

    filter_size = len(filters[0][0])
    assert all(len(filter_) == filter_size
               for dataset in filters for filter_ in dataset)
    packed_filters = [b''.join(binary_pack_filters(f, filter_size))
                      for f in filters]
    project_data, _ = create_project_upload_data(
        requests, packed_filters, result_type='groups',
        binary=True, hash_size=DATA_HASH_SIZE)
    try:
        run = post_run(requests, project_data, threshold=THRESHOLD)
        result_groups = get_run_result(requests, project_data, run)['groups']
    finally:
        delete_project(requests, project_data)
    
    # Compare ES result with anonlink.
    result_group_set = {frozenset(map(tuple, g)) for g in result_groups}
    true_group_set = set(map(frozenset, true_groups))
    assert result_group_set == true_group_set

