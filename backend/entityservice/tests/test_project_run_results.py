from entityservice.tests.util import create_project_no_data, post_run, get_run_result


def test_run_similarity_score_results(requests, similarity_scores_project, threshold):
    run_id = post_run(requests, similarity_scores_project, threshold)
    result = get_run_result(requests, similarity_scores_project, run_id, timeout=120)
    assert 'similarity_scores' in result
    for candidate_pair in result['similarity_scores']:
        assert 0.0 <= candidate_pair['sim'] >= 1.0
        for _, index in candidate_pair['group']:
            assert 0 <= index


def test_run_permutations_results(requests, permutations_project, threshold):
    run_id = post_run(requests, permutations_project, threshold)
    mask_result = get_run_result(requests, permutations_project, run_id, timeout=120)
    assert 'mask' in mask_result
    assert len(mask_result['mask']) == min(permutations_project['size'])

    # Get results using receipt_token A and B
    token1 = permutations_project['dp_responses'][0]['receipt_token']
    result1 = get_run_result(requests, permutations_project, run_id, token1, wait=False)
    assert 'permutation' in result1
    assert 'rows' in result1
    assert result1['rows'] == len(mask_result['mask'])

    token2 = permutations_project['dp_responses'][1]['receipt_token']
    result2 = get_run_result(requests, permutations_project, run_id, token2, wait=False)
    assert 'permutation' in result2
    assert 'rows' in result2
    assert result2['rows'] == result1['rows']
    assert result2['rows'] == len(mask_result['mask'])


def test_run_groups_results(requests, groups_project, threshold):
    run_id = post_run(requests, groups_project, threshold)
    result = get_run_result(requests, groups_project, run_id, timeout=120)
    
    assert 'groups' in result
    groups = result['groups']

    # All groups have at least two records
    assert all(len(g) >= 2 for g in groups)  
    
    # All records consist of a record index and dataset index
    assert all(all(len(i) == 2 for i in g) for g in groups)
    assert all(all(isinstance(i, int) and isinstance(j, int)
                   for i, j in g)
               for g in groups)


def test_run_mapping_results_no_data(requests):
    empty_project = create_project_no_data(requests)
    run_id = post_run(requests, empty_project, 0.95)
    get_run_result(requests, empty_project, run_id, expected_status=404, wait=False)
