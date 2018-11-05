from entityservice.database import DBConn, get_created_runs_and_queue, get_uploaded_encoding_sizes, \
    get_project_schema_encoding_size, get_project_encoding_size, set_project_encoding_size, logger, \
    check_project_exists, get_run, update_run_set_started, get_dataprovider_ids, update_encoding_metadata, \
    get_filter_metadata
from entityservice.errors import RunDeleted
from entityservice.models.run import progress_run_stage as progress_stage
from entityservice.tasks import delete_minio_objects
from entityservice.tasks.base_task import TracedTask
from entityservice.tasks.comparing import create_comparison_jobs
from entityservice.utils import clks_uploaded_to_project
from entityservice.async_worker import celery, logger
from entityservice.settings import Config as config


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
            # todo make sure this can be exposed to user
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
    log = logger.bind(pid=project_id)
    uploaded_encoding_sizes = get_uploaded_encoding_sizes(conn, project_id)
    first_uploaded_size = uploaded_encoding_sizes[0][1]
    schema_encoding_size = get_project_schema_encoding_size(conn, project_id)
    project_encoding_size = get_project_encoding_size(conn, project_id)
    # In order of preference:
    encoding_size = project_encoding_size or schema_encoding_size or first_uploaded_size
    log.debug(f"Uploaded encoding sizes: {uploaded_encoding_sizes}")
    log.debug(f"Encoding size set in schema: {schema_encoding_size}")
    log.debug(f"Project encoding size: {project_encoding_size}")

    log.info(f"Verifying uploads all have encoding size of {encoding_size} bytes.")
    for dp_id, enc_size in uploaded_encoding_sizes:
        if enc_size != encoding_size:
            log.warning(f"Set the encodings' upload state to error for dp={dp_id} and aborting processing")
            filename = get_filter_metadata(conn, dp_id)
            delete_minio_objects([filename,], project_id)
            update_encoding_metadata(conn, 'DELETED', dp_id, state='error')
            raise ValueError("Mismatch in encoding sizes. Stopping")
    if project_encoding_size is None:
        set_project_encoding_size(conn, project_id, encoding_size)


@celery.task(base=TracedTask, ignore_result=True, args_as_tags=('project_id', 'run_id'))
def compute_run(project_id, run_id, parent_span=None):
    log = logger.bind(pid=project_id, run_id=run_id)
    log.debug("Sanity check that we need to compute run")

    with DBConn() as conn:
        if not check_project_exists(conn, project_id):
            log.info("Project not found. Skipping")
            return

        res = get_run(conn, run_id)
        if res is None:
            log.info(f"Run not found. Skipping")
            raise RunDeleted(run_id)

        if res['state'] in {'completed', 'error'}:
            log.info("Run is already finished. Skipping")
            return
        if res['state'] == 'running':
            log.info("Run already started. Skipping")
            return

        log.debug("Setting run as in progress")
        update_run_set_started(conn, run_id)

        threshold = res['threshold']
        log.debug("Getting dp ids for compute similarity task")
        dp_ids = get_dataprovider_ids(conn, project_id)
        log.debug("Data providers: {}".format(dp_ids))
        assert len(dp_ids) == 2, "Only support two party comparisons at the moment"

    create_comparison_jobs.delay(project_id, run_id, dp_ids, threshold, compute_run.get_serialized_span())
    log.info("CLK similarity computation scheduled")

