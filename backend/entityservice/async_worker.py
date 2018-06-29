import csv
import io
import os
import random

import anonlink
import minio
from celery import Celery, chord
from celery.signals import after_setup_task_logger, after_setup_logger
from celery.utils.log import get_task_logger

from entityservice import cache
from entityservice.database import *
from entityservice.object_store import connect_to_object_store
from entityservice.serialization import binary_unpack_filters, \
    binary_pack_filters, bit_packed_element_size, deserialize_bitarray
from entityservice.settings import Config as config
from entityservice.utils import iterable_to_stream, fmt_bytes, clks_uploaded_to_project, generate_code, similarity_matrix_from_csv_bytes, \
    chain_streams
from entityservice.models.run import progress_run_stage as progress_stage

celery = Celery('tasks',
                broker=config.BROKER_URL,
                backend=config.CELERY_RESULT_BACKEND
                )

celery.conf.CELERY_TASK_SERIALIZER = 'json'
celery.conf.CELERY_ACCEPT_CONTENT = ['json']
celery.conf.CELERY_RESULT_SERIALIZER = 'json'
celery.conf.CELERY_ANNOTATIONS = config.CELERY_ANNOTATIONS
celery.conf.CELERYD_PREFETCH_MULTIPLIER = config.CELERYD_PREFETCH_MULTIPLIER
celery.conf.CELERYD_MAX_TASKS_PER_CHILD = config.CELERYD_MAX_TASKS_PER_CHILD
celery.conf.CELERY_ACKS_LATE = config.CELERY_ACKS_LATE
celery.conf.CELERY_ROUTES = config.CELERY_ROUTES


@after_setup_logger.connect
@after_setup_task_logger.connect
def init_celery_logger(logger, **kwargs):
    level = logging.DEBUG if config.DEBUG else logging.INFO

    for handler in logger.handlers[:]:
        handler.setFormatter(config.consoleFormat)
        handler.setLevel(level)

    logger.debug("Set logging up")


logger = get_task_logger(__name__)
logger.info("Setting up celery worker")


class BaseTask(celery.Task):
    """Abstract base class for all tasks in Entity Service"""

    abstract = True
    throws = (DBResourceMissing, psycopg2.IntegrityError)

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Log the exceptions to some central logging system at retry."""
        #todo captureException(exc)
        logger.warning("ON RETRY")

        super(BaseTask, self).on_retry(exc, task_id, args, kwargs, einfo)

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Log the exceptions"""
        logger.info("An exception '{}' was raised in a task".format(exc.__class__.__name__))

        if isinstance(exc, (DBResourceMissing, psycopg2.IntegrityError)):
            logger.info("Task was running when a resource was deleted, or db was inconsistent. Ignoring")
            # Note it will still be logged by celery
            # http://docs.celeryproject.org/en/master/userguide/tasks.html#Task.throws
            # todo captureException(exc)

        else:
            logger.exception(f"Unexpected exception raised in task {task_id}", exc_info=einfo)
            super(BaseTask, self).on_failure(exc, task_id, args, kwargs, einfo)


def convert_mapping_to_list(permutation):
    """Convert the permutation from a dict mapping into a list

    Assumes the keys and values of the given dict are numbers in the
    inclusive range from 0 to length. Note the keys should be int.

    Returns a list of the values from the passed dict - in the order
    defined by the keys.
    """
    l = len(permutation)

    perm_list = []
    for j in range(l):
        perm_list.append(permutation[j])
    return perm_list


@celery.task(base=BaseTask, ignore_result=True)
def handle_raw_upload(project_id, dp_id, receipt_token):
    logger.info("Project {} - handling user uploaded file for dp: {}".format(project_id, dp_id))
    with DBConn() as db:
        expected_size = get_number_of_hashes(db, dp_id)
    logger.info("Expecting to handle {} hashes".format(expected_size))

    mc = connect_to_object_store()

    # Input file is text, base64 encoded. One hash per line.
    raw_file = config.RAW_FILENAME_FMT.format(receipt_token)
    raw_data_response = mc.get_object(config.MINIO_BUCKET, raw_file)

    # Output file is binary
    filename = config.BIN_FILENAME_FMT.format(receipt_token)
    num_bytes = expected_size * bit_packed_element_size

    # Set up streaming processing pipeline
    buffered_stream = iterable_to_stream(raw_data_response.stream())
    text_stream = io.TextIOWrapper(buffered_stream, newline='\n')

    clkcounts = []

    def filter_generator():
        logger.debug("Deserializing json filters")
        for i, line in enumerate(text_stream):
            ba = deserialize_bitarray(line)
            yield (ba, i, ba.count())
            clkcounts.append(ba.count())

        logger.info("Processed {} hashes".format(len(clkcounts)))

    python_filters = filter_generator()
    # If small enough preload the data into our redis cache
    if expected_size < config.ENTITY_CACHE_THRESHOLD:
        logger.info("Caching pickled clk data")
        python_filters = list(python_filters)
        cache.set_deserialized_filter(dp_id, python_filters)
    else:
        logger.info("Not caching clk data as it is too large")

    packed_filters = binary_pack_filters(python_filters)

    packed_filter_stream = iterable_to_stream(packed_filters)

    logger.debug("Creating binary file with index, base64 encoded CLK, popcount")

    # Upload to object store
    logger.info("Uploading binary packed clks to object store. Size: {}".format(fmt_bytes(num_bytes)))
    mc.put_object(config.MINIO_BUCKET, filename, data=packed_filter_stream, length=num_bytes)

    with DBConn() as conn:
        update_filter_data(conn, filename, dp_id)

    # Now work out if all parties have added their data

    if clks_uploaded_to_project(project_id, check_data_ready=True):
        logger.info("Project {} - All parties data present. Scheduling any queued runs".format(project_id))
        check_for_executable_runs.delay(project_id)


@celery.task(base=BaseTask, ignore_result=True)
def check_for_executable_runs(project_id):
    """
    This is called when a run is posted (if project is ready for runs), and also
    after all dataproviders have uploaded CLKs, and the CLKS are ready.
    """
    logger.info("Checking for runs that need to be executed for project {}".format(project_id))
    if not clks_uploaded_to_project(project_id, check_data_ready=True):
        return

    with DBConn() as conn:
        new_runs = get_created_runs_and_queue(conn, project_id)
        logger.info("Creating tasks for {} created runs for project {}".format(len(new_runs), project_id))
        for qr in new_runs:
            run_id = qr[0]
            logger.info('Queueing run {} for computation'.format(qr))
            # Record that the run has reached a new stage
            progress_stage(conn, run_id)
            compute_run.delay(project_id, run_id)


@celery.task(base=BaseTask, ignore_result=True)
def compute_run(project_id, run_id):
    logger.debug("Sanity check that we need to compute run")

    with DBConn() as conn:
        res = get_run(conn, run_id)

        if res is None:
            logger.info(f"Run '{run_id}' not found. Skipping")
            raise RunDeleted(run_id)

        if res['state'] in {'completed', 'error'}:
            logger.info("Run '{}' is already finished. Skipping".format(run_id))
            return

        logger.debug("Setting run as in progress")
        update_run_set_started(conn, run_id)

        threshold = res['threshold']
        logger.debug("Getting dp ids for compute similarity task")
        dp_ids = get_dataprovider_ids(conn, project_id)
        logger.debug("Data providers: {}".format(dp_ids))
        assert len(dp_ids) == 2, "Only support two party comparisons at the moment"

    compute_similarity.delay(project_id, run_id, dp_ids, threshold)
    logger.info("CLK similarity computation scheduled")


@celery.task(base=BaseTask, ignore_result=True)
def compute_similarity(project_id, run_id, dp_ids, threshold):

    assert len(dp_ids) >= 2, "Expected at least 2 data providers"
    logger.info("Starting comparison of CLKs from data provider ids: {}, {}".format(dp_ids[0], dp_ids[1]))
    conn = connect_db()

    dataset_sizes = get_project_dataset_sizes(conn, project_id)
    if len(dataset_sizes) < 2:
        logger.warning("Unexpected number of dataset sizes in db. Stopping")
        update_run_mark_failure(conn, run_id)
        return
    else:
        lenf1, lenf2 = dataset_sizes

    # WOW Optiization TODO - We load all CLKS into memory in this task AND into redis!
    # Although now we don't load any CLKS into the redis cache
    # Prime the redis cache
    #filters1 = cache.get_deserialized_filter(dp_ids[0])
    #filters2 = cache.get_deserialized_filter(dp_ids[1])
    #lenf1 = len(filters1)
    #lenf2 = len(filters2)
    size = lenf1 * lenf2

    logger.info("Computing similarity for {} x {} entities".format(lenf1, lenf2))

    logger.info("Computing similarity using greedy method")

    filters1_object_filename = get_filter_metadata(conn, dp_ids[0])
    filters2_object_filename = get_filter_metadata(conn, dp_ids[1])

    logger.debug("Chunking computation task")
    chunk_size = config.get_task_chunk_size(size, threshold)
    if chunk_size is None:
        chunk_size = max(lenf1, lenf2)
    logger.info("Chunks will contain {} entities per task".format(chunk_size))
    update_run_chunk(conn, project_id, chunk_size)
    job_chunks = []

    dp1_chunks = []
    dp2_chunks = []

    for chunk_start_index_dp1 in range(0, lenf1, chunk_size):
        dp1_chunks.append(
            (filters1_object_filename, chunk_start_index_dp1, min(chunk_start_index_dp1 + chunk_size, lenf1))
        )
    for chunk_start_index_dp2 in range(0, lenf2, chunk_size):
        dp2_chunks.append(
            (filters2_object_filename, chunk_start_index_dp2, min(chunk_start_index_dp2 + chunk_size, lenf2))
        )

    # Every chunk in dp1 has to be run against every chunk in dp2
    for dp1_chunk in dp1_chunks:
        for dp2_chunk in dp2_chunks:
            job_chunks.append((dp1_chunk, dp2_chunk, ))

    logger.info("Chunking into {} computation tasks each with (at most) {} entities.".format(
        len(job_chunks), chunk_size))

    # Prepare the Celery Chord that will compute all the similarity scores:
    scoring_tasks = [compute_filter_similarity.si(chunk_dp1, chunk_dp2, project_id, run_id, threshold) for
                     chunk_dp1, chunk_dp2 in job_chunks]

    if len(scoring_tasks) == 1:
        scoring_tasks.append(celery_bug_fix.si())

    callback_task = aggregate_filter_chunks.s(project_id, run_id).on_error(on_chord_error.s(run_id=run_id))
    mapping_future = chord(scoring_tasks)(callback_task)


@celery.task()
def celery_bug_fix(*args, **kwargs):
    '''
    celery chords only correctly handle errors with at least 2 tasks,
    so we append a celery_bug_fix task.
    https://github.com/celery/celery/issues/3709
    '''
    return [0, None]


@celery.task(base=BaseTask, ignore_result=True)
def on_chord_error(*args, **kwargs):
    logger.info("An error occurred while processing the chord's tasks")
    with DBConn() as db:
        update_run_mark_failure(db, kwargs['run_id'])
    logger.warning("Marked run as failure")


@celery.task(base=BaseTask, ignore_result=True)
def save_and_permute(similarity_result, project_id, run_id):
    logger.debug("Saving and possibly permuting data")
    mapping = similarity_result['mapping']

    # Note Postgres requires JSON object keys to be strings
    # Celery actually converts the json arguments in the same way

    with DBConn() as db:
        result_type = get_project_column(db, project_id, 'result_type')

        # Just save the raw "mapping"
        logger.debug("Saving the resulting map data to the db")
        result_id = insert_mapping_result(db, run_id, mapping)
        dp_ids = get_dataprovider_ids(db, project_id)


    logger.info("Mapping result saved to db with id {}".format(result_id))

    if result_type == "permutations":
        logger.debug("Submitting job to permute mapping")
        permute_mapping_data.apply_async(
            (
                project_id,
                run_id,
                similarity_result['lenf1'],
                similarity_result['lenf2']
            )
        )
    else:
        logger.debug("Mark mapping job as complete")
        mark_mapping_complete.delay(run_id)

    # Post similarity computation cleanup
    logger.debug("Removing clk filters from redis cache")

    for dp_id in dp_ids:
        cache.remove_from_cache(dp_id)
    calculate_comparison_rate.delay()


@celery.task(base=BaseTask, ignore_result=True)
def permute_mapping_data(project_id, run_id, len_filters1, len_filters2):
    """
    Task which will create a permutation after a mapping has been completed.

    :param project_id: The project resource
    :param len_filters1:
    :param len_filters2:

    """
    db = connect_db()
    mapping_str = get_run_result(db, run_id)

    # Convert to int: int
    mapping = {int(k): int(mapping_str[k]) for k in mapping_str}

    logger.info("Creating random permutations")
    logger.debug("Entities in dataset A: {}, Entities in dataset B: {}".format(len_filters1, len_filters2))

    """
    Pack all the entities that match in the **same** random locations in both permutations.
    Then fill in all the gaps!

    Dictionaries first, then converted to lists.
    """
    smaller_dataset_size = min(len_filters1, len_filters2)
    logger.debug("Smaller dataset size is {}".format(smaller_dataset_size))
    number_in_common = len(mapping)
    a_permutation = {}  # Should be length of filters1
    b_permutation = {}  # length of filters2

    # By default mark all rows as NOT included in the mask
    mask = {i: False for i in range(smaller_dataset_size)}

    # start with all the possible indexes
    remaining_new_indexes = list(range(smaller_dataset_size))
    logger.info("Shuffling indices for matched entities")
    random.shuffle(remaining_new_indexes)
    logger.info("Assigning random indexes for {} matched entities".format(number_in_common))

    for mapping_number, a_index in enumerate(mapping):
        b_index = mapping[a_index]

        # Choose the index in the new mapping (randomly)
        mapping_index = remaining_new_indexes[mapping_number]

        a_permutation[a_index] = mapping_index
        b_permutation[b_index] = mapping_index

        # Mark the row included in the mask
        mask[mapping_index] = True

    remaining_new_indexes = set(remaining_new_indexes[number_in_common:])
    logger.info("Randomly adding all non matched entities")

    # Note the a and b datasets could be of different size.
    # At this point, both still have to use the remaining_new_indexes, and any
    # indexes that go over the number_in_common
    remaining_a_values = list(set(range(smaller_dataset_size, len_filters1)).union(remaining_new_indexes))
    remaining_b_values = list(set(range(smaller_dataset_size, len_filters2)).union(remaining_new_indexes))

    logger.debug("Shuffle the remaining indices")
    random.shuffle(remaining_a_values)
    random.shuffle(remaining_b_values)

    # For every element in a's permutation
    for a_index in range(len_filters1):
        # Check if it is not already present
        if a_index not in a_permutation:
            # This index isn't yet mapped

            # choose and remove a random index from the extended list of those that remain
            # note this "could" be the same row (a NOP 1-1 permutation)
            mapping_index = remaining_a_values.pop()

            a_permutation[a_index] = mapping_index

    # For every eventual element in a's permutation
    for b_index in range(len_filters2):
        # Check if it is not already present
        if b_index not in b_permutation:
            # This index isn't yet mapped

            # choose and remove a random index from the extended list of those that remain
            # note this "could" be the same row (a NOP 1-1 permutation)
            mapping_index = remaining_b_values.pop()
            b_permutation[b_index] = mapping_index

    logger.debug("Completed creating new permutations for each party")

    with db.cursor() as cur:
        dp_ids = get_dataprovider_ids(db, project_id)

        for i, permutation in enumerate([a_permutation, b_permutation]):
            # We convert here because celery and dicts with int keys don't play nice

            perm_list = convert_mapping_to_list(permutation)
            logger.debug("Saving a permutation")

            insert_permutation(cur, dp_ids[i], run_id, perm_list)

        logger.debug("Raw permutation data saved. Now saving raw mask")

        # Convert the mask dict to a list of 0/1 ints
        mask_list = convert_mapping_to_list({
                                                int(key): 1 if value else 0
                                                for key, value in mask.items()})

        logger.debug("Saving the mask")
        insert_permutation_mask(cur, project_id, run_id, mask_list)
        logger.info("Mask saved")
    db.commit()

    mark_mapping_complete.delay(run_id)


@celery.task(base=BaseTask, ignore_results=True)
def mark_mapping_complete(run_id):
    logger.debug("Marking run complete")
    with DBConn() as db:
        update_run_mark_complete(db, run_id)
    calculate_comparison_rate.delay()
    logger.info("Run {} marked as complete".format(run_id))


@celery.task(base=BaseTask)
def compute_filter_similarity(chunk_info_dp1, chunk_info_dp2, project_id, run_id, threshold):
    """Compute filter similarity between a chunk of filters in dataprovider 1,
    and a chunk of filters in dataprovider 2.

    :param chunk_info_dp1:
        A tuple containing:
            - object store filename
            - Chunk start index
            - Chunk stop index
    :param chunk_info_dp2:
    :param project_id:
    :param threshold:
    """
    logger.debug("Computing similarity for a chunk of filters")

    logger.debug("Checking that the resource exists (in case of job being canceled)")
    with DBConn() as db:
        if not check_run_exists(db, project_id, run_id):
            logger.info("Skipping as resource not found.")
            return None

    t0 = time.time()
    logger.debug("Fetching and deserializing chunk of filters for dataprovider 1")
    chunk_dp1, chunk_dp1_size = get_chunk_from_object_store(chunk_info_dp1)

    t1 = time.time()
    logger.debug("Fetching and deserializing chunk of filters for dataprovider 2")
    chunk_dp2, chunk_dp2_size = get_chunk_from_object_store(chunk_info_dp2)
    t2 = time.time()

    logger.debug("Calculating filter similarity")
    chunk_results = anonlink.entitymatch.calculate_filter_similarity(chunk_dp1, chunk_dp2,
                                                                     threshold=threshold,
                                                                     k=min(chunk_dp1_size, chunk_dp2_size),
                                                                     use_python=False)
    t3 = time.time()

    # Update the number of comparisons completed
    comparisons_computed = chunk_dp1_size * chunk_dp2_size
    save_current_progress(comparisons_computed, run_id)

    t4 = time.time()

    partial_sparse_result = []
    # offset chunk's index
    offset_dp1 = chunk_info_dp1[1]
    offset_dp2 = chunk_info_dp2[1]

    logger.debug("Offset DP1 by: {}, DP2 by: {}".format(offset_dp1, offset_dp2))
    for (ia, score, ib) in chunk_results:
        partial_sparse_result.append((ia + offset_dp1, ib + offset_dp2, score))

    t5 = time.time()

    num_results = len(partial_sparse_result)
    if num_results > 0:
        result_filename = 'chunk-res-{}.csv'.format(generate_code(12))
        logger.info("Writing {} intermediate results to file: {}".format(num_results, result_filename))

        with open(result_filename, 'wt') as f:
            csvwriter = csv.writer(f)
            csvwriter.writerows(partial_sparse_result)

        # Now write these to the object store. and return the filename and summary
        # Will write a csv file for now
        mc = connect_to_object_store()
        try:
            mc.fput_object(config.MINIO_BUCKET, result_filename, result_filename)
        except minio.ResponseError as err:
            logger.warning("Failed to store result in minio")
            raise

        # If we don't delete the file we *do* run out of space
        os.remove(result_filename)
    else:
        result_filename = None

    t6 = time.time()
    logger.info("run={} Comparisons: {}, Links above threshold: {}".format(run_id, comparisons_computed, len(chunk_results)))
    logger.info("Prep: {:.3f} + {:.3f}, Solve: {:.3f}, Progress: {:.3f}, Offset: {:.3f}, Save: {:.3f}, Total: {:.3f}".format(
        t1 - t0,
        t2 - t1,
        t3 - t2,
        t4 - t3,
        t4 - t4,
        t6 - t5,
        t6 - t0, )
    )

    return num_results, result_filename


def get_chunk_from_object_store(chunk_info):
    mc = connect_to_object_store()
    assert bit_packed_element_size == 134, "bit packed size doesn't match expectations"
    chunk_length = chunk_info[2] - chunk_info[1]
    chunk_bytes = bit_packed_element_size * chunk_length
    chunk_stream = mc.get_partial_object(config.MINIO_BUCKET, chunk_info[0], bit_packed_element_size * chunk_info[1], chunk_bytes)

    chunk_data = binary_unpack_filters(chunk_stream, chunk_bytes)

    return chunk_data, chunk_length


def save_current_progress(comparisons, run_id):
    logger.debug("Progress. Compared {} CLKS".format(comparisons))
    cache.update_progress(comparisons, run_id)


@celery.task(
    base=BaseTask,
    ignore_result=True,
    autoretry_for=(minio.ResponseError,),
    retry_backoff=True)
def aggregate_filter_chunks(similarity_result_files, project_id, run_id):
    if similarity_result_files is None: return
    mc = connect_to_object_store()
    files = []
    data_size = 0
    for num, filename in similarity_result_files:
        if num > 0:
            files.append(filename)
            data_size += mc.stat_object(config.MINIO_BUCKET, filename).size

    logger.debug("Aggregating result chunks from {} files, total size: {}".format(
        len(files), fmt_bytes(data_size)))

    result_file_stream_generator = (mc.get_object(config.MINIO_BUCKET, result_filename) for result_filename in files)

    logger.info("Similarity score results are {}".format(fmt_bytes(data_size)))
    result_stream = chain_streams(result_file_stream_generator)

    with DBConn() as db:
        result_type = get_project_column(db, project_id, 'result_type')

        # Note: Storing the similarity scores for all result types
        result_filename = store_similarity_scores(result_stream, run_id, data_size, db)

        if result_type == "similarity_scores":
            # Post similarity computation cleanup
            dp_ids = get_dataprovider_ids(db, project_id)

        else:
            # we promote the run to the next stage
            progress_stage(db, run_id)
            lenf1, lenf2 = get_project_dataset_sizes(db, project_id)

    # DB now committed, we can fire off tasks that depend on the new db state
    if result_type == "similarity_scores":
        logger.info("Deleting intermediate similarity score files from object store")
        mc.remove_objects(config.MINIO_BUCKET, files)
        logger.debug("Removing clk filters from redis cache")
        cache.remove_from_cache(dp_ids[0])
        cache.remove_from_cache(dp_ids[1])

        # Complete the run
        logger.info("Marking run {} as complete".format(run_id))
        mark_mapping_complete.delay(run_id)
    else:
        solver_task.delay(result_filename, project_id, run_id, lenf1, lenf2)


@celery.task(base=BaseTask, ignore_result=True)
def solver_task(similarity_scores_filename, project_id, run_id, lenf1, lenf2):
    mc = connect_to_object_store()
    score_file = mc.get_object(config.MINIO_BUCKET, similarity_scores_filename)
    logger.debug("Creating python sparse matrix from bytes data")
    sparse_matrix = similarity_matrix_from_csv_bytes(score_file.data)
    logger.info("Calculating the optimal mapping from similarity matrix")
    mapping = anonlink.entitymatch.greedy_solver(sparse_matrix)

    logger.debug("Converting all indices to strings")
    for key in mapping:
        mapping[key] = str(mapping[key])

    logger.info("Entity mapping has been computed")

    res = {
        "mapping": mapping,
        "lenf1": lenf1,
        "lenf2": lenf2
    }
    save_and_permute.delay(res, project_id, run_id)


def store_similarity_scores(buffer, run_id, length, conn):
    """
    Stores the similarity scores above a similarity threshold as a CSV in minio.

    :param buffer: a stream of csv bytes where each row contains similarity_scores:
                                - the index of an entity from dataprovider 1
                                - the index of an entity from dataprovider 1
                                - the similarity score between 0 and 1 of the best match
    :param run_id:
    :param length:
    """
    filename = config.SIMILARITY_SCORES_FILENAME_FMT.format(run_id)

    logger.info("Storing similarity score results in CSV file: {}".format(filename))
    mc = connect_to_object_store()
    mc.put_object(
        config.MINIO_BUCKET,
        filename,
        data=buffer,
        length=length,
        content_type='application/csv'
    )

    try:
        logger.debug("Storing the CSV filename '{}' in the database".format(filename))
        result_id = insert_similarity_score_file(conn, run_id, filename)
        logger.debug("Saved path to similarity scores file to db with id {}".format(result_id))
    except psycopg2.IntegrityError:
        logger.info("Error saving similarity score filename to database. Suspect that project has been deleted")
        raise RunDeleted(run_id)
    return filename


@celery.task(ignore_result=True)
def calculate_comparison_rate():
    dbinstance = connect_db()
    logger.info("Calculating global comparison rate")
    elapsed_run_time_query = """
        select run_id, project as project_id, (time_completed - time_started) as elapsed
        from runs
        WHERE
          runs.state='completed'
      """

    total_comparisons = 0
    total_time = timedelta(0)
    for run in query_db(dbinstance, elapsed_run_time_query):

        comparisons = get_total_comparisons_for_project(dbinstance, run['project_id'])

        if comparisons != 'NA':
            total_comparisons += comparisons
        else:
            logger.debug("Skipping run as it hasn't completed")
        total_time += run['elapsed']

    if total_time.total_seconds() > 0:
        rate = total_comparisons/total_time.total_seconds()
        logger.info("Total comparisons: {}".format(total_comparisons))
        logger.info("Total time:        {}".format(total_time.total_seconds()))
        logger.info("Comparison rate:   {}".format(rate))

        with dbinstance.cursor() as cur:
            insert_comparison_rate(cur, rate)

        dbinstance.commit()
    else:
        logger.warning("Can't compute comparison rate yet")
