import pytest

from entityservice.tests.config import url
from entityservice.tests.util import create_project_upload_fake_data, create_project_no_data, post_run, get_run_result


def test_run_mapping_results(requests, mapping_project):
    run_id = post_run(requests, mapping_project, 0.95)
    result = get_run_result(requests, mapping_project, run_id)
    assert 'mapping' in result
    assert isinstance(result['mapping'], dict)


def test_run_similarity_score_results(requests, similarity_scores_project, threshold):
    run_id = post_run(requests, similarity_scores_project, threshold)
    result = get_run_result(requests, similarity_scores_project, run_id)
    assert 'similarity_scores' in result


def test_run_permutation_unencrypted_results(requests, permutations_project, threshold):
    run_id = post_run(requests, permutations_project, threshold)
    mask_result = get_run_result(requests, permutations_project, run_id)
    assert 'mask' in mask_result
    assert len(mask_result['mask']) == min(permutations_project['size'])

    # Get results using receipt_token A and B
    token1 = permutations_project['dp_1']['receipt_token']
    result1 = get_run_result(requests, permutations_project, run_id, token1, wait=False)
    assert 'permutation' in result1
    assert 'rows' in result1
    assert result1['rows'] == len(mask_result['mask'])

    token2 = permutations_project['dp_2']['receipt_token']
    result2 = get_run_result(requests, permutations_project, run_id, token2, wait=False)
    assert 'permutation' in result2
    assert 'rows' in result2
    assert result2['rows'] == result1['rows']
    assert result2['rows'] == len(mask_result['mask'])


def test_run_mapping_results_no_data(requests):
    empty_project = create_project_no_data(requests)
    run_id = post_run(requests, empty_project, 0.95)
    result = get_run_result(requests, empty_project, run_id, expected_status = 404, wait=False)
