import array
import heapq
import itertools
import operator
import time

import anonlink
import minio
from celery import chord


from entityservice.async_worker import celery, logger
from entityservice.cache.encodings import remove_from_cache
from entityservice.cache.progress import save_current_progress
from entityservice.encoding_storage import get_encoding_chunk
from entityservice.errors import InactiveRun
from entityservice.database import (
    check_project_exists, check_run_exists, DBConn, get_dataprovider_ids,
    get_project_column, get_project_dataset_sizes,
    get_project_encoding_size, get_run, insert_similarity_score_file,
    update_run_mark_failure, get_block_metadata)
from entityservice.models.run import progress_run_stage as progress_stage
from entityservice.object_store import connect_to_object_store
from entityservice.settings import Config
from entityservice.tasks.base_task import TracedTask, celery_bug_fix, run_failed_handler
from entityservice.tasks.solver import solver_task
from entityservice.tasks import mark_run_complete
from entityservice.tasks.assert_valid_run import assert_valid_run
from entityservice.utils import generate_code, iterable_to_stream


def check_run_active(conn, project_id, run_id):
    """Raises InactiveRun if the project or run has been deleted from the database.
    """
    if not check_project_exists(conn, project_id) or not check_run_exists(conn, project_id, run_id):
        raise InactiveRun("Skipping as project or run not found in database.")


@celery.task(base=TracedTask, ignore_result=True, args_as_tags=('project_id', 'run_id'))
def create_comparison_jobs(project_id, run_id, parent_span=None):
    """Schedule all the entity comparisons as sub tasks for a run.

    At a high level this task:
    - checks if the project and run have been deleted and if so aborts.
    - retrieves metadata: the number and size of the datasets, the encoding size,
      and the number and size of blocks.
    - splits the work into independent "chunks" and schedules them to run in celery
    - schedules the follow up task to run after all the comparisons have been computed.
    """
    log = logger.bind(pid=project_id, run_id=run_id)
    current_span = create_comparison_jobs.span
    with DBConn() as conn:
        check_run_active(conn, project_id, run_id)

        dp_ids = get_dataprovider_ids(conn, project_id)
        number_of_datasets = len(dp_ids)
        assert number_of_datasets >= 2, "Expected at least 2 data providers"
        log.info(f"Scheduling comparison of CLKs from data provider ids: "
                 f"{', '.join(map(str, dp_ids))}")

        # Retrieve required metadata
        dataset_sizes, dp_block_sizes = _retrieve_blocked_dataset_sizes(conn, project_id, dp_ids)

        log.info("Finding blocks in common between dataproviders")
        common_blocks = _get_common_blocks(dp_block_sizes, dp_ids)

        if len(dataset_sizes) < 2:
            log.warning("Unexpected number of dataset sizes in db. Stopping")
            update_run_mark_failure(conn, run_id)
            return

        # We pass the encoding_size and threshold to the comparison tasks to minimize their db lookups
        encoding_size = get_project_encoding_size(conn, project_id)
        threshold = get_run(conn, run_id)['threshold']

    log.debug("Chunking computation task")
    # Create "chunks" of comparisons
    chunks = _create_work_chunks(common_blocks, dp_block_sizes, dp_ids, log)

    log.info(f"Computing similarity for "
             f"{' x '.join(map(str, dataset_sizes))} entities")
    current_span.log_kv({"event": 'get-dataset-sizes', 'sizes': dataset_sizes})


    log.info(f"Chunking into {len(chunks)} computation tasks")
    current_span.log_kv({"event": "chunking", 'num_chunks': len(chunks)})
    span_serialized = create_comparison_jobs.get_serialized_span()

    # Prepare the Celery Chord that will compute all the similarity scores:
    scoring_tasks = [compute_filter_similarity.si(
        chunk_info,
        project_id,
        run_id,
        threshold,
        encoding_size,
        span_serialized
    ) for chunk_info in chunks]

    if len(scoring_tasks) == 1:
        scoring_tasks.append(celery_bug_fix.si())

    callback_task = aggregate_comparisons.s(project_id=project_id, run_id=run_id, parent_span=span_serialized).on_error(
        run_failed_handler.s(run_id=run_id))
    future = chord(scoring_tasks)(callback_task)


def _create_work_chunks(blocks, dp_block_sizes, dp_ids, log, chunk_size_aim=Config.CHUNK_SIZE_AIM):
    """Create chunks of comparisons using blocking information.

    .. note::

        Ideally the chunks would be similarly sized, however with blocking the best we
        can do in this regard is to ensure a similar maximum size. Small blocks will
        directly translate to small chunks.

    :todo Consider passing all dataproviders to anonlink's `split_to_chunks` for a given
          large block instead of pairwise.

    :param blocks:
        dict mapping block identifier to a list of all combinations of
        data provider pairs containing this block. As created by :func:`_get_common_blocks`
    :param dp_block_sizes:
        A map from dataprovider id to a dict mapping
        block id to the number of encodings from the dataprovider in the
        block. As created by :func:`_retrieve_blocked_dataset_sizes`
    :param dp_ids: list of data provider ids
    :param log: A logger instance
    :param chunk_size_aim: The desired number of comparisons per chunk.

    :returns

        a dict describing the required comparisons. Comprised of:
        - dataproviderId - The dataprovider identifier in our database
        - datasetIndex - The dataprovider index [0, 1 ...]
        - block_id - The block of encodings this chunk is for
        - range - The range of encodings within the block that make up this chunk.
    """
    chunks = []
    for block_id in blocks:
        log.debug("Chunking block", block_id=block_id)
        # Note there might be many pairs of datasets in this block
        for dp1, dp2 in blocks[block_id]:
            size1 = dp_block_sizes[dp1][block_id]
            size2 = dp_block_sizes[dp2][block_id]

            comparisons = size1 * size2

            if comparisons > chunk_size_aim:
                log.debug("Block is too large for single task. Working out how to chunk it up")
                for chunk_info in anonlink.concurrency.split_to_chunks(chunk_size_aim,
                                                                       dataset_sizes=(size1, size2)):
                    # chunk_info's from anonlink already have datasetIndex of 0 or 1 and a range
                    # We need to correct the datasetIndex and add the database datasetId and add block_id.
                    add_dp_id_to_chunk_info(chunk_info, dp_ids, dp1, dp2)
                    add_block_id_to_chunk_info(chunk_info, block_id)
                    chunks.append(chunk_info)
            else:
                log.debug("Add the full block as a single work chunk")
                # Although the range "could" be optional we choose to make all chunk definitions consistent
                chunk_left = {"range": (0, size1), "block_id": block_id}
                chunk_right = {"range": (0, size2), "block_id": block_id}
                chunk_info = (chunk_left, chunk_right)
                add_dp_id_to_chunk_info(chunk_info, dp_ids, dp1, dp2)
                chunks.append(chunk_info)
    return chunks


def _get_common_blocks(dp_block_sizes, dp_ids):
    """Return all pairs of non-empty blocks across dataproviders.

    :returns
        dict mapping block identifier to a list of all combinations of
        data provider pairs containing this block.

        block_id -> List(pairs of dp ids)
        e.g. {'1': [(26, 27), (26, 28), (27, 28)]}
    """
    blocks = {}
    for dp1, dp2 in itertools.combinations(dp_ids, 2):
        # Get the intersection of blocks between these two dataproviders
        common_block_ids = set(dp_block_sizes[dp1]).intersection(set(dp_block_sizes[dp2]))
        for block_id in common_block_ids:
            blocks.setdefault(block_id, []).append((dp1, dp2))
    return blocks


def _retrieve_blocked_dataset_sizes(conn, project_id, dp_ids):
    """Fetch encoding counts for each dataset by block.

    :param dp_ids: Iterable of dataprovider database identifiers.
    :returns
        A 2-tuple of:

        - dataset sizes: a tuple of the number of encodings in each dataset.

        - dp_block_sizes: A map from dataprovider id to a dict mapping
          block id to the number of encodings from the dataprovider in the
          block.

          {dp_id -> {block_id -> block_size}}
          e.g. {33: {'1': 100}, 34: {'1': 100}, 35: {'1': 100}}
    """
    dataset_sizes = get_project_dataset_sizes(conn, project_id)

    dp_block_sizes = {}
    for dp_id in dp_ids:
        dp_block_sizes[dp_id] = dict(get_block_metadata(conn, dp_id))
    return dataset_sizes, dp_block_sizes


def add_dp_id_to_chunk_info(chunk_info, dp_ids, dp_id_left, dp_id_right):
    """
    Modify a chunk_info as returned by anonlink.concurrency.split_to_chunks
    to use correct project dataset indicies and add the database dp identifier.
    """
    dpindx = dict(zip(dp_ids, range(len(dp_ids))))

    left, right = chunk_info
    left['dataproviderId'] = dp_id_left
    left['datasetIndex'] = dpindx[dp_id_left]

    right['dataproviderId'] = dp_id_right
    right['datasetIndex'] = dpindx[dp_id_right]


def add_block_id_to_chunk_info(chunk_info, block_id):
    for chunk_dp_info in chunk_info:
        chunk_dp_info['block_id'] = block_id


@celery.task(base=TracedTask, args_as_tags=('project_id', 'run_id', 'threshold'))
def compute_filter_similarity(chunk_info, project_id, run_id, threshold, encoding_size, parent_span=None):
    """Compute filter similarity between a chunk of filters in dataprovider 1,
    and a chunk of filters in dataprovider 2.

    :param dict chunk_info:
        A chunk returned by ``anonlink.concurrency.split_to_chunks``.
    :param project_id:
    :param run_id:
    :param threshold:
    :param encoding_size: The size in bytes of each encoded entry
    :param parent_span: A serialized opentracing span context.
    :returns A 3-tuple: (num_results, result size in bytes, results_filename_in_object_store, )
    """
    log = logger.bind(pid=project_id, run_id=run_id)
    task_span = compute_filter_similarity.span

    def new_child_span(name):
        return compute_filter_similarity.tracer.start_active_span(name, child_of=compute_filter_similarity.span)

    log.debug("Computing similarity for a chunk of filters")

    log.debug("Checking that the resource exists (in case of run being canceled/deleted)")
    assert_valid_run(project_id, run_id, log)

    chunk_info_dp1, chunk_info_dp2 = chunk_info

    with DBConn() as conn:
        with new_child_span('fetching-left-encodings'):
            log.debug("Fetching and deserializing chunk of filters for dataprovider 1")
            chunk_with_ids_dp1, chunk_dp1_size = get_encoding_chunk(conn, chunk_info_dp1, encoding_size)
            #TODO: use the entity ids!
            entity_ids_dp1, chunk_dp1 = zip(*chunk_with_ids_dp1)

        with new_child_span('fetching-right-encodings'):
            log.debug("Fetching and deserializing chunk of filters for dataprovider 2")
            chunk_with_ids_dp2, chunk_dp2_size = get_encoding_chunk(conn, chunk_info_dp2, encoding_size)
            # TODO: use the entity ids!
            entity_ids_dp2, chunk_dp2 = zip(*chunk_with_ids_dp2)

    log.debug('Both chunks are fetched and deserialized')
    task_span.log_kv({'size1': chunk_dp1_size, 'size2': chunk_dp2_size, 'chunk_info': chunk_info})

    with new_child_span('comparing-encodings'):
        log.debug("Calculating filter similarity")
        try:
            sims, (rec_is0, rec_is1) = anonlink.similarities.dice_coefficient_accelerated(
                datasets=(chunk_dp1, chunk_dp2),
                threshold=threshold,
                k=min(chunk_dp1_size, chunk_dp2_size))

            def offset(recordarray, encoding_id_list):
                return array.array('I', [encoding_id_list[i] for i in recordarray])

            rec_is0 = offset(rec_is0, entity_ids_dp1)
            rec_is1 = offset(rec_is1, entity_ids_dp2)

        except NotImplementedError as e:
            log.warning("Encodings couldn't be compared using anonlink.")
            return

    log.debug('Encoding similarities calculated')

    with new_child_span('update-comparison-progress'):
        # Update the number of comparisons completed
        comparisons_computed = chunk_dp1_size * chunk_dp2_size
        save_current_progress(comparisons_computed, run_id)
        log.info("Comparisons: {}, Links above threshold: {}".format(comparisons_computed, len(sims)))

    with new_child_span('save-comparison-results-to-minio'):
        num_results = len(sims)

        if num_results:
            result_filename = Config.SIMILARITY_SCORES_FILENAME_FMT.format(
                generate_code(12))
            task_span.log_kv({"edges": num_results})
            log.info("Writing {} intermediate results to file: {}".format(num_results, result_filename))

            # Make index arrays for serialization
            index_1 = array.array('I', (chunk_info_dp1["datasetIndex"],)) * num_results
            index_2 = array.array('I', (chunk_info_dp2["datasetIndex"],)) * num_results

            chunk_results = sims, (index_1, index_2), (rec_is0, rec_is1),

            bytes_iter, file_size \
                = anonlink.serialization.dump_candidate_pairs_iter(chunk_results)
            iter_stream = iterable_to_stream(bytes_iter)

            mc = connect_to_object_store()
            try:
                mc.put_object(
                    Config.MINIO_BUCKET, result_filename, iter_stream, file_size)
            except minio.ResponseError as err:
                log.warning("Failed to store result in minio")
                raise
        else:
            result_filename = None
            file_size = None

    return num_results, file_size, result_filename


def _put_placeholder_empty_file(mc, log):
    sims = array.array('d')
    dset_is0 = array.array('I')
    dset_is1 = array.array('I')
    rec_is0 = array.array('I')
    rec_is1 = array.array('I')
    candidate_pairs = sims, (dset_is0, dset_is1), (rec_is0, rec_is1)
    empty_file_iter, empty_file_size \
        = anonlink.serialization.dump_candidate_pairs_iter(candidate_pairs)
    empty_file_name = Config.SIMILARITY_SCORES_FILENAME_FMT.format(
            generate_code(12))
    empty_file_stream = iterable_to_stream(empty_file_iter)
    try:
        mc.put_object(Config.MINIO_BUCKET, empty_file_name,
                      empty_file_stream, empty_file_size)
    except minio.ResponseError:
        log.warning("Failed to store empty result in minio.")
        raise
    return 0, empty_file_size, empty_file_name


def _merge_files(mc, log, file0, file1):
    num0, filesize0, filename0 = file0
    num1, filesize1, filename1 = file1
    total_num = num0 + num1
    file0_stream = mc.get_object(Config.MINIO_BUCKET, filename0)
    file1_stream = mc.get_object(Config.MINIO_BUCKET, filename1)
    merged_file_iter, merged_file_size \
        = anonlink.serialization.merge_streams_iter(
            (file0_stream, file1_stream), sizes=(filesize0, filesize1))
    merged_file_name = Config.SIMILARITY_SCORES_FILENAME_FMT.format(
            generate_code(12))
    merged_file_stream = iterable_to_stream(merged_file_iter)
    try:
        mc.put_object(Config.MINIO_BUCKET, merged_file_name,
                      merged_file_stream, merged_file_size)
    except minio.ResponseError:
        log.warning("Failed to store merged result in minio.")
        raise
    for del_err in mc.remove_objects(
            Config.MINIO_BUCKET, (filename0, filename1)):
        log.warning(f"Failed to delete result file "
                    f"{del_err.object_name}. {del_err}")
    return total_num, merged_file_size, merged_file_name


@celery.task(
    base=TracedTask,
    ignore_result=True,
    autoretry_for=(minio.ResponseError,),
    retry_backoff=True,
    args_as_tags=('project_id', 'run_id'))
def aggregate_comparisons(similarity_result_files, project_id, run_id, parent_span=None):
    log = logger.bind(pid=project_id, run_id=run_id)
    if similarity_result_files is None:
        raise TypeError("Inappropriate argument type - missing results files.")

    files = []
    for res in similarity_result_files:
        if res is None:
            log.warning("Missing results during aggregation. Stopping processing.")
            raise TypeError("Inappropriate argument type - results missing at aggregation step.")
        num, filesize, filename = res
        if num:
            assert filesize is not None
            assert filename is not None
            files.append((num, filesize, filename))
        else:
            assert filesize is None
            assert filename is None
    heapq.heapify(files)

    log.debug(f"Aggregating result chunks from {len(files)} files, "
              f"total size: {sum(map(operator.itemgetter(1), files))}")

    mc = connect_to_object_store()
    while len(files) > 1:
        file0 = heapq.heappop(files)
        file1 = heapq.heappop(files)
        merged_file = _merge_files(mc, log, file0, file1)
        heapq.heappush(files, merged_file)

    if not files:
        # No results. Let's chuck in an empty file.
        empty_file = _put_placeholder_empty_file(mc, log)
        files.append(empty_file)

    (merged_num, merged_filesize, merged_filename), = files
    log.info(f"Similarity score results in {merged_filename} in bucket "
             f"{Config.MINIO_BUCKET} take up {merged_filesize} bytes.")

    with DBConn() as db:
        result_type = get_project_column(db, project_id, 'result_type')
        result_id = insert_similarity_score_file(db, run_id, merged_filename)
        log.debug(f"Saved path to similarity scores file to db with id "
                  f"{result_id}")

        if result_type == "similarity_scores":
            # Post similarity computation cleanup
            dp_ids = get_dataprovider_ids(db, project_id)

        else:
            # we promote the run to the next stage
            progress_stage(db, run_id)
            dataset_sizes = get_project_dataset_sizes(db, project_id)

    # DB now committed, we can fire off tasks that depend on the new db state
    if result_type == "similarity_scores":
        log.debug("Removing clk filters from redis cache")
        for dp_id in dp_ids:
            remove_from_cache(dp_id)

        # Complete the run
        log.info("Marking run as complete")
        mark_run_complete.delay(run_id, aggregate_comparisons.get_serialized_span())
    else:
        solver_task.delay(
            merged_filename, project_id, run_id, dataset_sizes,
            aggregate_comparisons.get_serialized_span())
