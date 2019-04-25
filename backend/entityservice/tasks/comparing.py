import array
import csv
import heapq
import operator
import os
import time

import anonlink
import minio
import psycopg2
from celery import chord

from entityservice.utils import fmt_bytes
from entityservice.object_store import connect_to_object_store
from entityservice.async_worker import celery, logger
from entityservice.errors import DBResourceMissing, RunDeleted
from entityservice.database import (
    check_project_exists, check_run_exists, DBConn, get_dataprovider_ids,
    get_filter_metadata, get_project_column, get_project_dataset_sizes,
    get_project_encoding_size, get_run, insert_similarity_score_file,
    update_run_mark_failure)
from entityservice.models.run import progress_run_stage as progress_stage
from entityservice.serialization import get_chunk_from_object_store
from entityservice.settings import Config
from entityservice.tasks.base_task import TracedTask, celery_bug_fix, on_chord_error
from entityservice.tasks.solver import solver_task
from entityservice.tasks import mark_run_complete
from entityservice.cache import save_current_progress, remove_from_cache
from entityservice.utils import generate_code, iterable_to_stream


@celery.task(base=TracedTask, ignore_result=True, args_as_tags=('project_id', 'run_id', 'threshold'))
def create_comparison_jobs(project_id, run_id, parent_span=None):
    log = logger.bind(pid=project_id, run_id=run_id)
    with DBConn() as conn:

        dp_ids = get_dataprovider_ids(conn, project_id)
        assert len(dp_ids) >= 2, "Expected at least 2 data providers"
        log.info(f"Starting comparison of CLKs from data provider ids: "
                 f"{', '.join(map(str, dp_ids))}")
        current_span = create_comparison_jobs.span

        if not check_project_exists(conn, project_id) or not check_run_exists(conn, project_id, run_id):
            log.info("Skipping as project or run not found in database.")
            return

        run_info = get_run(conn, run_id)
        threshold = run_info['threshold']

        dataset_sizes = get_project_dataset_sizes(conn, project_id)

        if len(dataset_sizes) < 2:
            log.warning("Unexpected number of dataset sizes in db. Stopping")
            update_run_mark_failure(conn, run_id)
            return

        encoding_size = get_project_encoding_size(conn, project_id)

        log.info(f"Computing similarity for "
                 f"{' x '.join(map(str, dataset_sizes))} entities")
        current_span.log_kv({"event": 'get-dataset-sizes'})

        filters_object_filenames = tuple(
            get_filter_metadata(conn, dp_id) for dp_id in dp_ids)
        current_span.log_kv({"event": 'get-metadata'})

        log.debug("Chunking computation task")

    chunk_infos = tuple(anonlink.concurrency.split_to_chunks(
        Config.CHUNK_SIZE_AIM,
        dataset_sizes=dataset_sizes))

    # Save filenames with chunk information.
    for chunk_info in chunk_infos:
        for chunk_dp_info in chunk_info:
            chunk_dp_index = chunk_dp_info['datasetIndex']
            chunk_dp_store_filename = filters_object_filenames[chunk_dp_index]
            chunk_dp_info['storeFilename'] = chunk_dp_store_filename

    log.info(f"Chunking into {len(chunk_infos)} computation tasks")
    current_span.log_kv({"event": "chunking", 'num_chunks': len(chunk_infos)})
    span_serialized = create_comparison_jobs.get_serialized_span()

    # Prepare the Celery Chord that will compute all the similarity scores:
    scoring_tasks = [compute_filter_similarity.si(
        chunk_info,
        project_id,
        run_id,
        threshold,
        encoding_size,
        span_serialized
    ) for chunk_info in chunk_infos]

    if len(scoring_tasks) == 1:
        scoring_tasks.append(celery_bug_fix.si())

    callback_task = aggregate_comparisons.s(project_id, run_id, parent_span=span_serialized).on_error(
        on_chord_error.s(run_id=run_id))
    future = chord(scoring_tasks)(callback_task)


@celery.task(base=TracedTask, args_as_tags=('project_id', 'run_id', 'threshold'))
def compute_filter_similarity(chunk_info, project_id, run_id, threshold, encoding_size, parent_span=None):
    """Compute filter similarity between a chunk of filters in dataprovider 1,
    and a chunk of filters in dataprovider 2.

    :param chunk_info:
        Chunk info returned by ``anonlink.concurrency.split_to_chunks``.
        Additionally, "storeFilename" is added to each dataset chunk.
    :param project_id:
    :param threshold:
    :param encoding_size: The size in bytes of each encoded entry
    :param parent_span: A serialized opentracing span context.
    @returns A 2-tuple: (num_results, results_filename_in_object_store)
    """
    log = logger.bind(pid=project_id, run_id=run_id)
    log.debug("Computing similarity for a chunk of filters")
    span = compute_filter_similarity.span
    log.debug("Checking that the resource exists (in case of job being canceled)")
    with DBConn() as db:
        if not check_project_exists(db, project_id) or not check_run_exists(db, project_id, run_id):
            log.info("Failing task as project or run not found in database.")
            raise DBResourceMissing("project or run not found in database")

    chunk_info_dp1, chunk_info_dp2 = chunk_info

    t0 = time.time()
    log.debug("Fetching and deserializing chunk of filters for dataprovider 1")
    chunk_dp1, chunk_dp1_size = get_chunk_from_object_store(chunk_info_dp1, encoding_size)

    t1 = time.time()
    log.debug("Fetching and deserializing chunk of filters for dataprovider 2")
    chunk_dp2, chunk_dp2_size = get_chunk_from_object_store(chunk_info_dp2, encoding_size)
    t2 = time.time()
    span.log_kv({'event': 'chunks are fetched and deserialized'})
    log.debug("Calculating filter similarity")
    span.log_kv({'size1': chunk_dp1_size, 'size2': chunk_dp2_size})
    chunk_results = anonlink.concurrency.process_chunk(
        chunk_info,
        (chunk_dp1, chunk_dp2),
        anonlink.similarities.dice_coefficient_accelerated,
        threshold,
        k=min(chunk_dp1_size, chunk_dp2_size))
    t3 = time.time()
    span.log_kv({'event': 'similarities calculated'})

    # Update the number of comparisons completed
    comparisons_computed = chunk_dp1_size * chunk_dp2_size
    save_current_progress(comparisons_computed, run_id)

    t4 = time.time()

    sims, _, _ = chunk_results
    num_results = len(sims)

    if num_results:
        result_filename = Config.SIMILARITY_SCORES_FILENAME_FMT.format(
            generate_code(12))
        log.info("Writing {} intermediate results to file: {}".format(num_results, result_filename))

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
    t5 = time.time()

    log.info("run={} Comparisons: {}, Links above threshold: {}".format(run_id, comparisons_computed, len(chunk_results)))
    log.info("Prep: {:.3f} + {:.3f}, Solve: {:.3f}, Progress: {:.3f}, Save: {:.3f}, Total: {:.3f}".format(
        t1 - t0,
        t2 - t1,
        t3 - t2,
        t4 - t3,
        t5 - t4,
        t5 - t0)
    )
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


def _insert_similarity_into_db(db, log, run_id, merged_filename):
    try:
        result_id = insert_similarity_score_file(
            db, run_id, merged_filename)
    except psycopg2.IntegrityError:
        log.info("Error saving similarity score filename to database. "
                 "The project may have been deleted.")
        raise RunDeleted(run_id)
    log.debug(f"Saved path to similarity scores file to db with id "
              f"{result_id}")


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

        _insert_similarity_into_db(db, log, run_id, merged_filename)

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
