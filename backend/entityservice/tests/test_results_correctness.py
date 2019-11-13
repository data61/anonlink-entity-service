import pickle
import os

import anonlink
import pytest

from entityservice.tests.util import create_project_upload_data, post_run, get_run_result, delete_project


# !!! We assume that anonlink computes the right results.
# we test if the results provided by the entity service through the API are the same as locally computed with anonlink.


@pytest.fixture
def the_truth(scope='module'):
    threshold = 0.8
    with open(os.path.join(os.path.dirname(os.path.realpath(__file__)),'testdata/febrl4_clks_and_truth.pkl'), 'rb') as f:
        # load prepared clks and ground truth from file
        filters_a, filters_b, entity_ids_a, entity_ids_b, clks_a, clks_b = pickle.load(f)
        # compute similarity scores with anonlink
        candidate_pairs = anonlink.candidate_generation.find_candidate_pairs(
            (filters_a, filters_b),
            anonlink.similarities.dice_coefficient_accelerated,
            threshold,
            k=len(filters_a))
        sims, _, (rec_is_a, rec_is_b) = candidate_pairs

        groups = anonlink.solving.greedy_solve(candidate_pairs)

        similarity_scores = {(a, b): sim
                             for sim, a, b in zip(sims, rec_is_a, rec_is_b)}

        yield {'entity_ids_a': entity_ids_a,
               'entity_ids_b': entity_ids_b,
               'similarity_scores': similarity_scores,
               'groups': groups,
               'threshold': threshold,
               'clks_a': clks_a,
               'clks_b': clks_b}


def test_similarity_scores(requests, the_truth):
    project_data, _ = create_project_upload_data(
        requests,
        (the_truth['clks_a'], the_truth['clks_b']),
        result_type='similarity_scores')
    run = post_run(requests, project_data, threshold=the_truth['threshold'])
    result = get_run_result(requests, project_data, run, timeout=60)
    
    true_scores = the_truth['similarity_scores']
    result_scores = {tuple(index for _, index in sorted(candidate_pair['group'])): candidate_pair['sim']
                     for candidate_pair in result['similarity_scores']}

    # Anonlink is more strict on enforcing the k parameter. Hence the
    # subset.
    assert true_scores.keys() <= result_scores.keys()

    for pair in true_scores:
        assert true_scores[pair] == result_scores[pair]

    delete_project(requests, project_data)


def test_permutation(requests, the_truth):
    project_data, (r_a, r_b) = create_project_upload_data(
        requests,
        (the_truth['clks_a'], the_truth['clks_b']),
        result_type='permutations')
    run = post_run(requests, project_data, threshold=the_truth['threshold'])
    mask_result = get_run_result(requests, project_data, run, timeout=60)
    perm_a_result = get_run_result(requests, project_data, run, result_token=r_a['receipt_token'], wait=False)
    perm_b_result = get_run_result(requests, project_data, run, result_token=r_b['receipt_token'], wait=False)
    # compare permutations and mask against mapping of the truth
    permutation_a = inverse_of_permutation(perm_a_result['permutation'])
    permutation_b = inverse_of_permutation(perm_b_result['permutation'])
    groups = the_truth['groups']
    # Use a mapping output to simplify the checking.
    mapping = dict(anonlink.solving.pairs_from_groups(groups))

    # NB: Anonlink is more strict on enforcing the k parameter, so there
    # is a small chance the below won't hold. This should only be the
    # case for more noisy problems.
    for a, b, m in zip(permutation_a, permutation_b, mask_result['mask']):
        if m == 1:
            assert a in mapping, f"Unexpected link was included - run {run}"
            assert mapping[a] == b, f"Expected link from {a} was incorrect - run {run}"
        else:
            assert a not in mapping, f"Expected link was masked out - run {run}"


def test_groups(requests, the_truth):
    project_data, _ = create_project_upload_data(
        requests,
        (the_truth['clks_a'], the_truth['clks_b']),
        result_type='groups')
    run = post_run(requests, project_data, threshold=the_truth['threshold'])
    result = get_run_result(requests, project_data, run)
    # compare mapping with the truth
    result_groups = result['groups']
    true_groups = the_truth['groups']

    result_groups = frozenset(frozenset(map(tuple, group))
                              for group in result_groups)
    true_groups = frozenset(map(frozenset, true_groups))

    assert result_groups == true_groups


def apply_permutation(items, permutation):
    perm_items = items.copy()
    for item, newpos in zip(items, permutation):
        perm_items[newpos] = item
    return perm_items


def inverse_of_permutation(permutation):
    """ Let's be 'p' the entry of a permutation 'P' at position 'i'.
        The permutation is applied to a vector x as:
        P(x) = y with y_p = x_i
        (Take the element at position 'i' and put it at pos 'p')
        The inverse of a permutation is defined as:
        P^{}-1 (x) = y with y_i = x_p """
    return apply_permutation(list(range(len(permutation))), permutation)
