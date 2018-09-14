
from entityservice.tests.util import post_run, delete_project


def test_delete_mapping_project_after_creating_run_with_clks(requests, mapping_project):
    post_run(requests, mapping_project, 0.9)
    delete_project(requests, mapping_project)


def test_delete_similarity_project_after_creating_run_with_clks(requests, similarity_scores_project):
    post_run(requests, similarity_scores_project, 0.9)
    delete_project(requests, similarity_scores_project)


def test_delete_permutations_project_after_creating_run_with_clks(requests, permutations_project):
    post_run(requests, permutations_project, 0.9)
    delete_project(requests, permutations_project)
