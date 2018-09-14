import io
import math
import random
import time

import anonlink
import psycopg2.extras
from celery import Celery, chord
from celery.signals import after_setup_task_logger, after_setup_logger
from celery.utils.log import get_task_logger

import entityservice.cache
from entityservice import cache
from entityservice.database import *
from entityservice.object_store import connect_to_object_store
from entityservice.serialization import binary_unpack_filters, \
    binary_pack_filters, deserialize_filters, bit_packed_element_size, deserialize_bitarray
from entityservice.settings import Config as config
from entityservice.utils import chunks, iterable_to_stream, fmt_bytes
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


def clks_uploaded_to_project(project_id):
    """ See if the given mapping has had all parties contribute data.
    """
    logger.info("Counting contributing parties")
    conn = connect_db()
    parties_contributed = get_number_parties_uploaded(conn, project_id)
    number_parties = get_project_column(conn, project_id, 'parties')
    logger.info("{}/{} parties have contributed clks".format(parties_contributed, number_parties))
    return parties_contributed == number_parties


@celery.task()
def handle_raw_upload(project_id, dp_id, receipt_token):
    logger.info("Project {} - handling user uploaded file for dp: {}".format(project_id, dp_id))
    expected_size = get_number_of_hashes(connect_db(), dp_id)
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

    update_filter_data(connect_db(), filename, dp_id)

    # Now work out if all parties have added their data

    if clks_uploaded_to_project(project_id):
        logger.info("Project {} - All parties data present. Scheduling any queued runs".format(project_id))
        check_for_executable_runs.delay(project_id)


@celery.task()
def check_for_executable_runs(project_id):
    """
    This is called when a run is posted (if project is ready for runs), and also
    after all dataproviders have uploaded CLKs.
    """
    logger.info("Checking for runs that need to be executed for project {}".format(project_id))

    conn = connect_db()

    if clks_uploaded_to_project(project_id):
        new_runs = get_created_runs_and_queue(conn, project_id)

        if new_runs is not None:
            logger.info("Creating tasks for {} created runs for project {}".format(len(new_runs), project_id))
            for qr in new_runs:
                run_id = qr[0]
                logger.info('queueing run {} for computation'.format(qr))
                # run has reached a new stage
                progress_stage(conn, run_id)
                compute_run.delay(project_id, run_id)


@celery.task()
def compute_run(project_id, run_id):
    logger.debug("Sanity check that we need to compute run")

    conn = connect_db()
    res = get_run(conn, run_id)

    if res['state'] in {'completed', 'error'}:
        logger.info("Run '{}' is already finished. Skipping".format(run_id))
        return

    logger.debug("Setting run as in progress")
    with conn.cursor() as cur:
        cur.execute("""UPDATE runs SET
                      time_started = now(),
                      state = 'running'
                    WHERE
                      run_id = %s
                    """,
                    [run_id])
    conn.commit()

    threshold = res['threshold']
    logger.debug("Getting dp ids for compute similarity task")
    dp_ids = get_dataprovider_ids(conn, project_id)

    logger.debug("Data providers: {}".format(dp_ids))
    assert len(dp_ids) == 2, "Only support two party comparisons at the moment"

    compute_similarity.delay(project_id, run_id, dp_ids, threshold)

    logger.info("CLK similarity computation scheduled")

    return 'Done'


@celery.task()
def compute_similarity(project_id, run_id, dp_ids, threshold):
    """

    """

    logger.info("Starting comparison of CLKs from data provider ids: {}, {}".format(dp_ids[0], dp_ids[1]))
    conn = connect_db()

    lenf1, lenf2 = get_project_dataset_sizes(conn, project_id)

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

    callback_task = aggregate_filter_chunks.s(project_id, run_id, lenf1, lenf2).on_error(on_chord_error.s(run_id=run_id))
    mapping_future = chord(scoring_tasks)(callback_task)


@celery.task()
def celery_bug_fix(*args, **kwargs):
    '''
    celery chords only correctly handle errors with at least 2 tasks,
    so we append a celery_bug_fix task.
    https://github.com/celery/celery/issues/3709
    '''
    return []


@celery.task()
def on_chord_error(*args, **kwargs):
    logger.info("An error occurred while processing the chord's tasks")
    conn = connect_db()
    update_run_mark_failure(conn, kwargs['run_id'])
    logger.warning("Marked run as failure")


@celery.task()
def save_and_permute(similarity_result, project_id, run_id):
    logger.debug("Saving and possibly permuting data")
    mapping = similarity_result['mapping']

    # Note Postgres requires JSON object keys to be strings
    # Celery actually converts the json arguments in the same way

    db = connect_db()
    result_type = get_project_column(db, project_id, 'result_type')

    # Just save the raw "mapping"
    logger.debug("Saving the resulting map data to the db")
    result_id = insert_mapping_result(db, run_id, mapping)
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

    dp_ids = get_dataprovider_ids(db, project_id)
    cache.remove_from_cache(dp_ids[0])
    cache.remove_from_cache(dp_ids[1])
    calculate_comparison_rate.delay()


@celery.task()
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


@celery.task()
def mark_mapping_complete(run_id):
    logger.debug("Marking run complete")
    db = connect_db()
    update_run_mark_complete(db, run_id)
    logger.info("run {} marked as complete".format(run_id))


@celery.task()
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
            logger.warning("Skipping as resource not found.")
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
    logger.info("Timings: Prep: {:.4f} + {:.4f}, Solve: {:.4f}, Total: {:.4f}  Comparisons: {}".format(
        t1-t0, t2-t1, t3-t2, t3-t0, comparisons_computed)
    )

    save_current_progress(comparisons_computed, run_id)

    partial_sparse_result = []
    # offset chunk's index
    offset_dp1 = chunk_info_dp1[1]
    offset_dp2 = chunk_info_dp2[1]

    logger.debug("Offset DP1 by: {}, DP2 by: {}".format(offset_dp1, offset_dp2))
    for (ia, score, ib) in chunk_results:
        partial_sparse_result.append((ia + offset_dp1, score, ib + offset_dp2))

    return partial_sparse_result


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


@celery.task()
def aggregate_filter_chunks(sparse_result_groups, project_id, run_id, lenf1, lenf2):
    sparse_matrix = []
    # Need to handle a single result group because 'chord(array_of_tasks, next_task)' won't wrap the
    # result in a list when there is only one task in the array.
    # (See https://github.com/celery/celery/issues/3597)
    if all(len(sparse_result_group) == 3 for sparse_result_group in sparse_result_groups):
        logger.debug("Only received one task chunk")
        sparse_matrix = sparse_result_groups
    else:
        logger.debug("Aggregating chunks")
        for partial_sparse_result in sparse_result_groups:
            sparse_matrix.extend(partial_sparse_result)

    db = connect_db()
    result_type = get_project_column(db, project_id, 'result_type')

    if result_type == "similarity_scores":
        logger.info("Store the similarity scores in a CSV file")
        store_similarity_scores.delay(sparse_matrix, project_id, run_id)
    else:
        # we promote the run to the next stage
        progress_stage(db, run_id)
        # As we have the entire sparse matrix in memory at this point we directly compute the mapping
        # instead of re-serializing and calling another task
        logger.info("Calculating the optimal mapping from similarity matrix of length {}".format(len(sparse_matrix)))
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


@celery.task()
def store_similarity_scores(similarity_scores, project_id, run_id):
    """
    Stores the similarity scores above a similarity threshold as a CSV in minio.

    :param similarity_scores: a list of tuples consisting of:
                                - the index of an entity from dataprovider 1
                                - the similarity score between 0 and 1 of the best match
                                - the index of an entity from dataprovider 1
    :param project_id: the resource ID of the mapping
    """
    filename = config.SIMILARITY_SCORES_FILENAME_FMT.format(run_id)

    # Generate a CSV-like string from aggregated chunks
    # Also need to make sure this can handle very large list
    def csv_generator():
        for row in similarity_scores:
            # Rearrange the elements in the row from
            #   `entity_1`, `score`, `entity_2`
            # to
            #   `entity_1`, `entity_2`, `score`
            # before storing the row in a CSV file
            row[0], row[1], row[2] = row[0], row[2], row[1]
            content = ','.join(map(str, row)).encode() + b'\n'
            yield content

    data = b''.join(csv_generator())
    buffer = io.BytesIO(data)

    logger.debug("Store the the aggregated chunks")
    mc = connect_to_object_store()
    mc.put_object(
        config.MINIO_BUCKET,
        filename,
        data=buffer,
        length=len(data),
        content_type='application/csv'
    )

    db = connect_db()
    logger.debug("Storing the CSV filename: {}".format(filename))
    with db.cursor() as cur:
        result_id = execute_returning_id(cur, """
            INSERT into similarity_scores
              (run, file)
            VALUES
              (%s, %s)
            RETURNING id;
            """,
            [
                run_id, filename
            ])
    db.commit()
    logger.debug("Saved path to similarity scores file to db with id {}".format(result_id))

    # Complete mapping job
    logger.debug("Marking run as complete")
    mark_mapping_complete.delay(run_id)

    # Post similarity computation cleanup
    logger.debug("Removing clk filters from redis cache")

    dp_ids = get_dataprovider_ids(db, project_id)
    cache.remove_from_cache(dp_ids[0])
    cache.remove_from_cache(dp_ids[1])
    calculate_comparison_rate.delay()


@celery.task()
def calculate_comparison_rate():
    dbinstance = connect_db()
    logger.info("Calculating comparison rate")
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
