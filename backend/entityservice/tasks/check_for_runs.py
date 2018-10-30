from entityservice.async_worker import celery, logger, compute_run
from entityservice.database import DBConn, get_created_runs_and_queue, get_uploaded_encoding_sizes, \
    get_project_schema_encoding_size, get_project_encoding_size, set_project_encoding_size
from entityservice.models.run import progress_run_stage as progress_stage
from entityservice.tasks.base_task import TracedTask
from entityservice.utils import clks_uploaded_to_project


@celery.task(base=TracedTask, ignore_result=True, args_as_tags=('project_id',))
def check_for_executable_runs(project_id, parent_span=None):
    """
    This is called when a run is posted (if project is ready for runs), and also
    after all dataproviders have uploaded CLKs, and the CLKS are ready.
    """
    log = logger.bind(pid=project_id)
    log.info("Checking for runs that need to be executed")
    if not clks_uploaded_to_project(project_id, check_data_ready=True):
        return

    with DBConn() as conn:
        try:
            check_and_set_project_encoding_size(project_id, conn)
        except ValueError as e:
            log.warning(e.args[0])
            return

        new_runs = get_created_runs_and_queue(conn, project_id)
        log.info("Creating tasks for {} created runs for project {}".format(len(new_runs), project_id))
        for qr in new_runs:
            run_id = qr[0]
            log.info('Queueing run for computation', run_id=run_id)
            # Record that the run has reached a new stage
            progress_stage(conn, run_id)
            compute_run.delay(project_id, run_id, check_for_executable_runs.get_serialized_span())


def check_and_set_project_encoding_size(project_id, conn):
    # Check for consistency between uploaded encodings and commit to a
    # project encoding size if one wasn't provided in the linkage schema
    uploaded_encoding_sizes = get_uploaded_encoding_sizes(conn, project_id)
    schema_encoding_size = get_project_schema_encoding_size(conn, project_id)
    project_encoding_size = get_project_encoding_size(conn, project_id)
    encoding_size = project_encoding_size or schema_encoding_size or uploaded_encoding_sizes[0]
    if not all(encoding_size == enc_size for enc_size in uploaded_encoding_sizes):
        raise ValueError("Mismatch in encoding sizes. Stopping")
    if project_encoding_size is None:
        set_project_encoding_size(conn, project_id, encoding_size)
