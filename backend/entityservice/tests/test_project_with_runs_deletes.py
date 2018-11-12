
from entityservice.tests.util import post_run, delete_project, create_project_upload_fake_data


def test_deleteproject_after_creating_run_with_clks(requests, result_type):
    project, dp1, dp2 = create_project_upload_fake_data(requests, [100, 100], overlap=0.5, result_type=result_type)
    post_run(requests, project, 0.9)
    delete_project(requests, project)
