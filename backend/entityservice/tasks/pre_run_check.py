from entityservice.async_worker import celery, logger
from entityservice.database import DBConn, get_created_runs_and_queue, get_uploaded_encoding_sizes, \
    get_project_schema_encoding_size, get_project_encoding_size, set_project_encoding_size, \
    update_project_mark_all_runs_failed
from entityservice.models.run import progress_run_stage as progress_stage
from entityservice.settings import Config as config
from entityservice.tasks.base_task import TracedTask
from entityservice.error_checking import handle_invalid_encoding_data
from entityservice.tasks.run import prerun_check
from entityservice.utils import clks_uploaded_to_project


@celery.task(base=TracedTask, ignore_result=True, args_as_tags=('project_id',))
def check_for_executable_runs(project_id, parent_span=None):
    """
    This is called when a run is posted (if project is ready for runs), and also
    after all dataproviders have uploaded CLKs, and the CLKS are ready.
    """
    log = logger.bind(pid=project_id)
    log.debug("Checking for runs that need to be executed")
    if not clks_uploaded_to_project(project_id, check_data_ready=True):
        return

    with DBConn() as conn:
        try:
            check_and_set_project_encoding_size(project_id, conn)
        except ValueError as e:
            log.warning(e.args[0])
            # make sure this error can be exposed to user by marking the run/s as failed
            update_project_mark_all_runs_failed(conn, project_id, str(e))
            return
        new_runs = get_created_runs_and_queue(conn, project_id)

        log.debug("Progressing run stages")
        for qr in new_runs:
            # Record that the run has reached a new stage
            run_id = qr[0]
            progress_stage(conn, run_id)

    # commit db changes before scheduling following tasks
    log.debug("Creating tasks for {} created runs for project {}".format(len(new_runs), project_id))
    for qr in new_runs:
        run_id = qr[0]
        log.info('Queueing run for computation', run_id=run_id)
        prerun_check.delay(project_id, run_id, check_for_executable_runs.get_serialized_span())


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
            handle_invalid_encoding_data(project_id, dp_id)
            raise ValueError("Mismatch in encoding sizes. Stopping")
    if project_encoding_size is None:
        set_project_encoding_size(conn, project_id, encoding_size)

    if not config.MIN_ENCODING_SIZE <= encoding_size <= config.MAX_ENCODING_SIZE:
        # Set all uploads to error state
        for dp_id, _ in uploaded_encoding_sizes:
            handle_invalid_encoding_data(project_id, dp_id)
        raise ValueError("Encoding size out of configured bounds")

    if encoding_size % 8:
        raise ValueError("Encoding size must be multiple of 8 bytes (64 bits)")
