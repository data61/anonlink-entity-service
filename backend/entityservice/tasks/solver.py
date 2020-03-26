import anonlink
from anonlink.candidate_generation import _merge_similarities

from entityservice.object_store import connect_to_object_store
from entityservice.async_worker import celery, logger
from entityservice.settings import Config as config
from entityservice.tasks.base_task import TracedTask
from entityservice.tasks.permutation import save_and_permute


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

    log.info(f"Number of candidate pairs before deduplication: {len(candidate_pairs_with_duplicates[0])}")
    if len(candidate_pairs_with_duplicates[0]) > 0:
        # TODO use public interface when available
        # https://github.com/data61/anonlink/issues/271
        candidate_pairs = _merge_similarities([zip(similarity_scores, dset_is0, dset_is1, rec_is0, rec_is1)], k=None)
        log.info(f"Number of candidate pairs after deduplication: {len(candidate_pairs[0])}")

        log.info("Calculating the optimal mapping from similarity matrix")
        groups = anonlink.solving.greedy_solve(candidate_pairs)
    else:
        groups = []

    log.info("Entity groups have been computed")

    res = {
        "groups": groups,
        "datasetSizes": dataset_sizes
    }
    save_and_permute.delay(res, project_id, run_id, solver_task.get_serialized_span())
