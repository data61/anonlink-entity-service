from array import array

import anonlink

from entityservice.object_store import connect_to_object_store
from entityservice.async_worker import celery, logger
from entityservice.settings import Config as config
from entityservice.tasks.base_task import TracedTask
from entityservice.tasks.permutation import save_and_permute
from entityservice.utils import deduplicate_sorted_iter


@celery.task(base=TracedTask, ignore_result=True, args_as_tags=('project_id', 'run_id'))
def solver_task(similarity_scores_filename, project_id, run_id, dataset_sizes, parent_span):
    log = logger.bind(pid=project_id, run_id=run_id)
    mc = connect_to_object_store()
    solver_task.span.log_kv({'datasetSizes': dataset_sizes,
                             'filename': similarity_scores_filename})
    score_file = mc.get_object(config.MINIO_BUCKET, similarity_scores_filename)
    log.debug("Creating python sparse matrix from bytes data")
    candidate_pairs_with_duplicates = anonlink.serialization.load_candidate_pairs(score_file)
    similarity_scores, (dset_is0, dset_is1), (rec_is0, rec_is1) = candidate_pairs_with_duplicates
    float_typecode = similarity_scores.typecode
    int_typecode = dset_is0.typecode
    log.info(f"Number of candidate pairs before deduplication: {len(candidate_pairs_with_duplicates[0])}")
    dedup_iter = deduplicate_sorted_iter(zip(similarity_scores, dset_is0, dset_is1, rec_is0, rec_is1))
    # Convert back to typed arrays before solving
    similarity_scores, dset_is0, dset_is1, rec_is0, rec_is1 = zip(*dedup_iter)
    similarity_scores, dset_is0, dset_is1, rec_is0, rec_is1 = array(float_typecode, similarity_scores), \
                                                              array(int_typecode, dset_is0), \
                                                              array(int_typecode, dset_is1), \
                                                              array(int_typecode, rec_is0), \
                                                              array(int_typecode, rec_is1)
    candidate_pairs = similarity_scores, (dset_is0, dset_is1), (rec_is0, rec_is1)
    log.info(f"Number of candidate pairs after deduplication: {len(candidate_pairs[0])}")

    log.info("Calculating the optimal mapping from similarity matrix")

    groups = anonlink.solving.greedy_solve(candidate_pairs)

    log.info("Entity groups have been computed")

    res = {
        "groups": groups,
        "datasetSizes": dataset_sizes
    }
    save_and_permute.delay(res, project_id, run_id, solver_task.get_serialized_span())
