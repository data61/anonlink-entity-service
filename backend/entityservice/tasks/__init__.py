from entityservice.tasks.base_task import BaseTask, TracedTask

from entityservice.tasks.stats import calculate_comparison_rate
from entityservice.tasks.mark_run_complete import mark_run_complete
from entityservice.tasks.project_cleanup import delete_minio_objects, remove_project
from entityservice.tasks.pre_run_check import check_for_executable_runs
from entityservice.tasks.assert_valid_run import assert_valid_run
from entityservice.tasks.run import prerun_check
from entityservice.tasks.encoding_uploading import handle_raw_upload, pull_external_data_encodings_only, \
    pull_external_data, handle_upload_error
from entityservice.tasks.comparing import create_comparison_jobs, compute_filter_similarity, aggregate_comparisons
from entityservice.tasks.permutation import save_and_permute, permute_mapping_data
from entityservice.tasks.solver import solver_task
