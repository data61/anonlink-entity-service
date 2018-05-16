import pickle
import os

import anonlink
import pytest

from entityservice.tests.util import create_project_upload_data, post_run, get_run_result


# !!! We assume that anonlink computes the right results.
# we test if the results provided by the entity service through the API are the same as locally computed with anonlink.


@pytest.fixture
def the_truth(scope='module'):
    threshold = 0.8
    with open(os.path.join(os.path.dirname(os.path.realpath(__file__)),'testdata/febrl4_clks_and_truth.pkl'), 'rb') as f:
        # load prepared clks and ground truth from file
        filters_a, filters_b, entity_ids_a, entity_ids_b, clks_a, clks_b = pickle.load(f)
        # compute similarity scores with anonlink
        sparse_matrix = anonlink.entitymatch.calculate_filter_similarity(filters_a, filters_b, k=len(filters_a),
                                                                         threshold=threshold)
        # compute mapping with anonlink
        mapping = anonlink.entitymatch.greedy_solver(sparse_matrix)
        yield {'entity_ids_a': entity_ids_a,
               'entity_ids_b': entity_ids_b,
               'similarity_scores': sparse_matrix,
               'mapping': mapping,
               'threshold': threshold,
               'clks_a': clks_a,
               'clks_b': clks_b}


def test_similarity_scores(requests, the_truth):
    project_data, _, _ = create_project_upload_data(requests, the_truth['clks_a'], the_truth['clks_b'],
                                                    result_type='similarity_scores')
    run = post_run(requests, project_data, threshold=the_truth['threshold'])
    result = get_run_result(requests, project_data, run)
    # compare the result with the truth
    ss = result['similarity_scores']
    ts = the_truth['similarity_scores']
    assert len(ss) == len(ts)
    for es_score, true_score in zip(ss, ts):
        assert es_score[0] == true_score[0] and es_score[1] == true_score[2]
        assert es_score[2] == pytest.approx(true_score[1], 1e-10), 'similarity scores are different'


def test_mapping(requests, the_truth):
    project_data, _, _ = create_project_upload_data(requests, the_truth['clks_a'], the_truth['clks_b'],
                                                    result_type='mapping')
    run = post_run(requests, project_data, threshold=the_truth['threshold'])
    result = get_run_result(requests, project_data, run)
    # compare mapping with the truth
    mapping = {int(k): int(result['mapping'][k]) for k in result['mapping']}
    assert mapping.keys() == the_truth['mapping'].keys()
    for key, value in mapping.items():
        assert value == the_truth['mapping'][key]
        assert the_truth['entity_ids_a'][key] == the_truth['entity_ids_b'][value]


def test_permutation(requests, the_truth):
    project_data, r_a, r_b = create_project_upload_data(requests, the_truth['clks_a'], the_truth['clks_b'],
                                                        result_type='permutations')
    run = post_run(requests, project_data, threshold=the_truth['threshold'])
    mask_result = get_run_result(requests, project_data, run)
    perm_a_result = get_run_result(requests, project_data, run, result_token=r_a['receipt_token'], wait=False)
    perm_b_result = get_run_result(requests, project_data, run, result_token=r_b['receipt_token'], wait=False)
    # compare permutations and mask against mapping of the truth
    idx_a_after_perm = reverse_permutation(perm_a_result['permutation'])
    idx_b_after_perm = reverse_permutation(perm_b_result['permutation'])
    mapping = the_truth['mapping']
    for a, b, m in zip(idx_a_after_perm, idx_b_after_perm, mask_result['mask']):
        if m == 1:
            assert mapping[a] == b
        else:
            assert a not in mapping


def apply_permutation(items, permutation):
    neworder = items.copy()
    for item, newpos in zip(items, permutation):
        neworder[newpos] = item
    return neworder


def reverse_permutation(permutations):
    return apply_permutation(list(range(len(permutations))), permutations)
