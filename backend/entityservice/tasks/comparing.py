import array
import heapq
import itertools
import operator

from minio.deleteobjects import DeleteObject
from minio.error import MinioException

import anonlink
import minio
from celery import chord


from entityservice.async_worker import celery, logger
from entityservice.cache.encodings import remove_from_cache
from entityservice.cache.progress import get_candidate_count_for_run, save_current_progress
from entityservice.encoding_storage import get_encoding_chunk, get_encoding_chunks
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
    - splits the work into independent "packages" and schedules them to run in celery
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
        dataset_sizes, dp_block_sizes, dp_lookups = _retrieve_blocked_dataset_sizes_and_lookup(conn, project_id, dp_ids)

        log.info("Finding blocks in common between dataproviders")
        common_blocks = _get_common_blocks(dp_block_sizes, dp_ids)

        # We pass the encoding_size and threshold to the comparison tasks to minimize their db lookups
        encoding_size = get_project_encoding_size(conn, project_id)
        threshold = get_run(conn, run_id)['threshold']

    log.debug("creating work packages for computation tasks")
    packages = _create_work_packages(common_blocks, dp_block_sizes, dp_ids, log, block_lookups=dp_lookups)

    log.info(f"Chunking into {len(packages)} computation tasks")
    current_span.log_kv({"event": "chunking", 'num_chunks': len(packages), 'dataset-sizes': dataset_sizes})
    span_serialized = create_comparison_jobs.get_serialized_span()

    # Prepare the Celery Chord that will compute all the similarity scores:
    scoring_tasks = [compute_filter_similarity.si(
        package,
        project_id,
        run_id,
        threshold,
        encoding_size,
        span_serialized
    ) for package in packages]

    if len(scoring_tasks) == 1:
        scoring_tasks.append(celery_bug_fix.si())

    callback_task = aggregate_comparisons.s(project_id=project_id, run_id=run_id, parent_span=span_serialized).on_error(
        run_failed_handler.s(run_id=run_id))
    log.info(f"Scheduling comparison tasks")
    future = chord(scoring_tasks)(callback_task)


def _create_work_packages(blocks, dp_block_sizes, dp_ids, log, block_lookups, chunk_size_aim=Config.CHUNK_SIZE_AIM):
    """Create packages of chunks of comparisons using blocking information.

    If a block is too large, that is, if the required comparisons is larger than the chunk size aim, then we split
    the block into several chunks. If blocks are smaller, than multiple blocks are bundled into one package.

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
    packages = []
    MAX_CHUNKS_PER_PACKAGE = 100000
    cur_package = []
    cur_comparisons = 0

    for block_name, (dp1, dp2) in blocks:
        size1 = dp_block_sizes[dp1][block_name]
        size2 = dp_block_sizes[dp2][block_name]
        num_comparisons = size1 * size2
        if num_comparisons > chunk_size_aim:
            if len(cur_package) > 0:
                packages.append(cur_package)
                cur_package = []
                cur_comparisons = 0
            log.debug("Block is too large for single task. Working out how to chunk it up")
            for chunk_info in anonlink.concurrency.split_to_chunks(chunk_size_aim,
                                                                   dataset_sizes=(size1, size2)):
                # chunk_info's from anonlink already have datasetIndex of 0 or 1 and a range
                # We need to correct the datasetIndex and add the database datasetId and add block_id.
                add_dp_id_to_chunk_info(chunk_info, dp_ids, dp1, dp2)
                left, right = chunk_info
                left['block_id'] = block_lookups[dp1][block_name]
                right['block_id'] = block_lookups[dp2][block_name]
                packages.append([chunk_info])
        else:
            chunk_left = {"range": (0, size1), "block_id": block_lookups[dp1][block_name]}
            chunk_right = {"range": (0, size2), "block_id": block_lookups[dp2][block_name]}
            chunk_info = (chunk_left, chunk_right)
            add_dp_id_to_chunk_info(chunk_info, dp_ids, dp1, dp2)
            # if there is still enough capacity in the current work package, then append, otherwise new package
            if cur_comparisons + num_comparisons <= chunk_size_aim and len(cur_package) < MAX_CHUNKS_PER_PACKAGE:
                cur_package.append(chunk_info)
                cur_comparisons += num_comparisons
            else:
                packages.append(cur_package)
                cur_package = [chunk_info]
                cur_comparisons = num_comparisons
    # the last package might not have been added to the packages yet.
    if len(cur_package) > 0:
        packages.append(cur_package)
    return packages


def _get_common_blocks(dp_block_sizes, dp_ids):
    """Return all pairs of non-empty blocks across dataproviders.

    :returns
        dict mapping block identifier to a list of all combinations of
        data provider pairs containing this block.

        block_id -> List(pairs of dp ids)
        e.g. {'1': [(26, 27), (26, 28), (27, 28)]}
    """
    for dp1, dp2 in itertools.combinations(dp_ids, 2):
        # Get the intersection of blocks between these two dataproviders
        common_block_ids = set(dp_block_sizes[dp1]).intersection(set(dp_block_sizes[dp2]))
        for block_id in common_block_ids:
            yield block_id, (dp1, dp2)


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


def _retrieve_blocked_dataset_sizes_and_lookup(conn, project_id, dp_ids):
    """Fetch encoding counts for each dataset by block. And create lookup table from block_name to block_id

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
    dp_block_lookups = {}
    for dp_id in dp_ids:
        block_sizes = {}
        lookup = {}
        for block_name, block_id, count in get_block_metadata(conn, dp_id):
            block_sizes[block_name] = count
            lookup[block_name] = block_id
        dp_block_sizes[dp_id] = block_sizes
        dp_block_lookups[dp_id] = lookup
    return dataset_sizes, dp_block_sizes, dp_block_lookups


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
def compute_filter_similarity(package, project_id, run_id, threshold, encoding_size, parent_span=None):
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

    def new_child_span(name, parent_scope=None):
        log.debug(f"Entering span '{name}'")
        if parent_scope is None:
            parent_scope = compute_filter_similarity
        return compute_filter_similarity.tracer.start_active_span(name, child_of=parent_scope.span)

    log.debug(f"Computing similarities for {len(package)} chunks of filters")
    log.debug("Checking that the resource exists (in case of run being canceled/deleted)")
    assert_valid_run(project_id, run_id, log)

    def reindex_using_encoding_ids(recordarray, encoding_id_list):
        # Map results from "index in chunk" to encoding id.
        return array.array('I', [encoding_id_list[i] for i in recordarray])

    num_results = 0
    num_comparisons = 0
    sim_results = []

    with DBConn() as conn:
        if len(package) > 1:  # multiple full blocks in one package
            with new_child_span(f'fetching-encodings of package of size {len(package)}'):
                package = get_encoding_chunks(conn, package, encoding_size=encoding_size)
        else:  # this chunk is all part of one block
            with new_child_span(f'fetching-encodings of package with 1 chunk'):
                chunk_info_dp1, chunk_info_dp2 = package[0]
                chunk_with_ids_dp1, chunk_dp1_size = get_encoding_chunk(conn, chunk_info_dp1, encoding_size)
                entity_ids_dp1, chunk_dp1 = zip(*chunk_with_ids_dp1)
                chunk_info_dp1['encodings'] = chunk_dp1
                chunk_info_dp1['entity_ids'] = entity_ids_dp1
                chunk_with_ids_dp2, chunk_dp2_size = get_encoding_chunk(conn, chunk_info_dp2, encoding_size)
                entity_ids_dp2, chunk_dp2 = zip(*chunk_with_ids_dp2)
                chunk_info_dp2['encodings'] = chunk_dp2
                chunk_info_dp2['entity_ids'] = entity_ids_dp2
    log.debug('All encodings for package are fetched and deserialized')
    log.debug("Calculating filter similarities for work package")

    with new_child_span('comparing-encodings') as parent_scope:
        for chunk_number, (chunk_dp1, chunk_dp2) in enumerate(package):
            with new_child_span(f'comparing chunk {chunk_number}', parent_scope=parent_scope) as scope:
                enc_dp1 = chunk_dp1['encodings']
                enc_dp1_size = len(enc_dp1)
                enc_dp2 = chunk_dp2['encodings']
                enc_dp2_size = len(enc_dp2)
                assert enc_dp1_size > 0, "Zero sized chunk in dp1"
                assert enc_dp2_size > 0, "Zero sized chunk in dp2"
                scope.span.set_tag('num_encodings_1', enc_dp1_size)
                scope.span.set_tag('num_encodings_2', enc_dp2_size)

                log.debug("Calling anonlink with encodings", num_encodings_1=enc_dp1_size, num_encodings_2=enc_dp2_size)
                try:
                    sims, (rec_is0, rec_is1) = anonlink.similarities.dice_coefficient_accelerated(
                        datasets=(enc_dp1, enc_dp2),
                        threshold=threshold,
                        k=min(enc_dp1_size, enc_dp2_size))
                except NotImplementedError as e:
                    log.warning(f"Encodings couldn't be compared using anonlink. {e}")
                    return
                rec_is0 = reindex_using_encoding_ids(rec_is0, chunk_dp1['entity_ids'])
                rec_is1 = reindex_using_encoding_ids(rec_is1, chunk_dp2['entity_ids'])
                num_results += len(sims)
                num_comparisons += enc_dp1_size * enc_dp2_size
                sim_results.append((sims, (rec_is0, rec_is1), chunk_dp1['datasetIndex'], chunk_dp2['datasetIndex']))
        log.debug(f'comparison is done. {num_comparisons} comparisons got {num_results} pairs above the threshold')

    # progress reporting
    log.debug('Encoding similarities calculated')

    with new_child_span('update-comparison-progress') as scope:
        # Update the number of comparisons completed
        save_current_progress(num_comparisons, num_results, run_id)
        scope.span.log_kv({'comparisons': num_comparisons, 'num_similar': num_results})
        log.debug("Comparisons: {}, Links above threshold: {}".format(num_comparisons, num_results))

    with new_child_span('check-within-candidate-limits') as scope:
        global_candidates_for_run = get_candidate_count_for_run(run_id)
        scope.span.log_kv({'global candidate count for run': global_candidates_for_run})

        if global_candidates_for_run is not None and global_candidates_for_run > Config.SIMILARITY_SCORES_MAX_CANDIDATE_PAIRS:
            log.warning(f"This run has created more than the global limit of candidate pairs. Setting state to 'error'")
            with DBConn() as conn:
                update_run_mark_failure(conn, run_id,
                                        'This run has created more than the global limit of candidate pairs.')
            return

    # Save results file into minio
    with new_child_span('save-comparison-results-to-minio'):

        file_iters = []
        file_sizes = []
        for sims, (rec_is0, rec_is1), dp1_ds_idx, dp2_ds_idx in sim_results:
            num_sims = len(sims)

            if num_sims:
                # Make index arrays for serialization
                index_1 = array.array('I', (dp1_ds_idx,)) * num_sims
                index_2 = array.array('I', (dp2_ds_idx,)) * num_sims
                chunk_results = sims, (index_1, index_2), (rec_is0, rec_is1),
                bytes_iter, file_size \
                    = anonlink.serialization.dump_candidate_pairs_iter(chunk_results)
                file_iters.append(iterable_to_stream(bytes_iter))
                file_sizes.append(file_size)

        if len(file_iters) > 1:
            # we need to merge them first into one ordered thingy
            merged_file_iter, merged_file_size \
                = anonlink.serialization.merge_streams_iter(file_iters, sizes=file_sizes)
            merged_file_iter = iterable_to_stream(merged_file_iter)
        elif len(file_iters) == 1:
            merged_file_iter = file_iters[0]
            merged_file_size = file_sizes[0]
        else:
            return 0, None, None

        result_filename = Config.SIMILARITY_SCORES_FILENAME_FMT.format(
            generate_code(12))
        task_span.log_kv({"edges": num_results})
        log.info("Writing {} intermediate results to file: {}".format(num_results, result_filename))

        mc = connect_to_object_store()
        try:
            mc.put_object(
                Config.MINIO_BUCKET, result_filename, merged_file_iter, merged_file_size)
        except minio.S3Error as err:
            log.warning("Failed to store result in minio: {}".format(err))
            raise

    return num_results, merged_file_size, result_filename


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
    except minio.S3Error:
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
    merged_file_stream = iterable_to_stream(_unique_values_iter(merged_file_iter))
    try:
        # as we don't know the file size because we removed duplicates, we just do a multipart upload of 100MB junks.
        mc.put_object(Config.MINIO_BUCKET, merged_file_name,
                      merged_file_stream, length=-1, part_size=100*1024*1024)

    except MinioException:
        log.warning("Failed to store merged result in minio.")
        raise
    delete_objects = [DeleteObject(f) for f in (filename0, filename1)]
    for del_err in mc.remove_objects(Config.MINIO_BUCKET, delete_objects):
        log.warning(f"Failed to delete result file "
                    f"{del_err.object_name}. {del_err}")
    return total_num, merged_file_size, merged_file_name


def _unique_values_iter(iterable):
    """ yields only the unique values of a **sorted** iterable """
    it = iter(iterable)
    previous = next(it)
    yield previous
    for item in it:
        if item != previous:
            previous = item
            yield item


@celery.task(
    base=TracedTask,
    ignore_result=True,
    autoretry_for=(MinioException,),
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
             f"{Config.MINIO_BUCKET} may take up up to {merged_filesize} bytes.")

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
