
import csv
import os
import time

import anonlink
import minio
from celery import chord

from entityservice.utils import fmt_bytes
from entityservice.object_store import connect_to_object_store
from entityservice.async_worker import celery, logger
from entityservice.errors import DBResourceMissing
from entityservice.database import check_project_exists, check_run_exists, \
    get_project_dataset_sizes, update_run_mark_failure, get_project_encoding_size, get_filter_metadata, \
    update_run_chunk, DBConn, get_project_column, get_dataprovider_ids, get_run
from entityservice.models.run import progress_run_stage as progress_stage
from entityservice.object_store import store_similarity_scores
from entityservice.serialization import get_chunk_from_object_store
from entityservice.settings import Config
from entityservice.tasks.base_task import TracedTask, celery_bug_fix, on_chord_error
from entityservice.tasks.solver import solver_task
from entityservice.tasks import mark_run_complete
from entityservice.cache import save_current_progress, remove_from_cache
from entityservice.utils import generate_code, chain_streams


@celery.task(base=TracedTask, ignore_result=True, args_as_tags=('project_id', 'run_id', 'threshold'))
def create_comparison_jobs(project_id, run_id, parent_span=None):
    log = logger.bind(pid=project_id, run_id=run_id)
    with DBConn() as conn:

        dp_ids = get_dataprovider_ids(conn, project_id)
        assert len(dp_ids) >= 2, "Expected at least 2 data providers"
        log.info("Starting comparison of CLKs from data provider ids: {}, {}".format(dp_ids[0], dp_ids[1]))
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
        else:
            lenf1, lenf2 = dataset_sizes

        encoding_size = get_project_encoding_size(conn, project_id)

        size = lenf1 * lenf2

        log.info("Computing similarity for {} x {} entities".format(lenf1, lenf2))
        current_span.log_kv({"event": 'get-dataset-sizes'})

        filters1_object_filename = get_filter_metadata(conn, dp_ids[0])
        filters2_object_filename = get_filter_metadata(conn, dp_ids[1])
        current_span.log_kv({"event": 'get-metadata'})

        log.debug("Chunking computation task")
        chunk_size = Config.get_task_chunk_size(size, threshold)
        if chunk_size is None:
            chunk_size = max(lenf1, lenf2)
        log.info("Chunks will contain {} entities per task".format(chunk_size))
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

    log.info("Chunking into {} computation tasks each with (at most) {} entities.".format(
        len(job_chunks), chunk_size))
    current_span.log_kv({"event": "chunking", "chunksize": chunk_size, 'num_chunks': len(job_chunks)})
    span_serialized = create_comparison_jobs.get_serialized_span()

    # Prepare the Celery Chord that will compute all the similarity scores:
    scoring_tasks = [compute_filter_similarity.si(
        chunk_dp1,
        chunk_dp2,
        project_id,
        run_id,
        threshold,
        encoding_size,
        span_serialized
    ) for chunk_dp1, chunk_dp2 in job_chunks]

    if len(scoring_tasks) == 1:
        scoring_tasks.append(celery_bug_fix.si())

    callback_task = aggregate_comparisons.s(project_id, run_id, parent_span=span_serialized).on_error(
        on_chord_error.s(run_id=run_id))
    future = chord(scoring_tasks)(callback_task)


@celery.task(base=TracedTask, args_as_tags=('project_id', 'run_id', 'threshold'))
def compute_filter_similarity(chunk_info_dp1, chunk_info_dp2, project_id, run_id, threshold, encoding_size, parent_span=None):
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
    chunk_results = anonlink.candidate_generation.find_candidate_pairs(
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

    partial_sparse_result = []
    # offset chunk's index
    offset_dp1 = chunk_info_dp1[1]
    offset_dp2 = chunk_info_dp2[1]

    log.debug("Offset DP1 by: {}, DP2 by: {}".format(offset_dp1, offset_dp2))
    sims, _, (rec_is0, rec_is1) = chunk_results
    for score, ia, ib in zip(sims, rec_is0, rec_is1):
        partial_sparse_result.append((ia + offset_dp1, ib + offset_dp2, score))

    t5 = time.time()

    num_results = len(partial_sparse_result)
    if num_results > 0:
        result_filename = 'chunk-res-{}.csv'.format(generate_code(12))
        log.info("Writing {} intermediate results to file: {}".format(num_results, result_filename))

        with open(result_filename, 'wt') as f:
            csvwriter = csv.writer(f)
            csvwriter.writerows(partial_sparse_result)

        # Now write these to the object store. and return the filename and summary
        # Will write a csv file for now
        mc = connect_to_object_store()
        try:
            mc.fput_object(Config.MINIO_BUCKET, result_filename, result_filename)
        except minio.ResponseError as err:
            log.warning("Failed to store result in minio")
            raise

        # If we don't delete the file we *do* run out of space
        os.remove(result_filename)
    else:
        result_filename = None
    t6 = time.time()

    log.info("run={} Comparisons: {}, Links above threshold: {}".format(run_id, comparisons_computed, len(chunk_results)))
    log.info("Prep: {:.3f} + {:.3f}, Solve: {:.3f}, Progress: {:.3f}, Offset: {:.3f}, Save: {:.3f}, Total: {:.3f}".format(
        t1 - t0,
        t2 - t1,
        t3 - t2,
        t4 - t3,
        t4 - t4,
        t6 - t5,
        t6 - t0)
    )
    return num_results, result_filename


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
    mc = connect_to_object_store()
    files = []
    data_size = 0

    for res in similarity_result_files:
        if res is None:
            log.warning("Missing results during aggregation. Stopping processing.")
            raise TypeError("Inappropriate argument type - results missing at aggregation step.")
        else:
            num, filename = res

        if num > 0:
            files.append(filename)
            data_size += mc.stat_object(Config.MINIO_BUCKET, filename).size

    log.debug("Aggregating result chunks from {} files, total size: {}".format(
        len(files), fmt_bytes(data_size)))

    result_file_stream_generator = (mc.get_object(Config.MINIO_BUCKET, result_filename) for result_filename in files)

    log.info("Similarity score results are {}".format(fmt_bytes(data_size)))
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
        log.info("Deleting intermediate similarity score files from object store")
        mc.remove_objects(Config.MINIO_BUCKET, files)
        log.debug("Removing clk filters from redis cache")
        remove_from_cache(dp_ids[0])
        remove_from_cache(dp_ids[1])

        # Complete the run
        log.info("Marking run as complete")
        mark_run_complete.delay(run_id, aggregate_comparisons.get_serialized_span())
    else:
        solver_task.delay(result_filename, project_id, run_id, lenf1, lenf2, aggregate_comparisons.get_serialized_span())
