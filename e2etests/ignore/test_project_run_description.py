from e2etests.util import create_project_upload_fake_data, post_run, get_run


def test_run_description_missing_run(requests, project):
    _ = get_run(requests, project, 'invalid', expected_status=403)
