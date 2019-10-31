
from entityservice.tests.util import post_run, get_run_status, is_run_status, \
    create_project_no_data, ensure_run_progressing


def test_permutations_run_status_with_clks_2p(requests, permutations_project):
    size = permutations_project['size']
    ensure_run_progressing(requests, permutations_project, size)


def test_similarity_scores_run_status_with_clks_2p(requests, similarity_scores_project):
    size = similarity_scores_project['size']
    ensure_run_progressing(requests, similarity_scores_project, size)


def test_groups_run_status_with_clks_np(requests, groups_project):
    size = groups_project['size']
    ensure_run_progressing(requests, groups_project, size)


def test_run_status_without_clks(requests):
    project = create_project_no_data(requests)

    run_id = post_run(requests, project, 0.9)
    status = get_run_status(requests, project, run_id)

    is_run_status(status)
    assert status['state'] == 'created'
