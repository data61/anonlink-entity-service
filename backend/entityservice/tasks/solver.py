import anonlink

from entityservice.object_store import connect_to_object_store
from entityservice.async_worker import celery, logger
from entityservice.settings import Config as config
from entityservice.tasks.base_task import TracedTask
from entityservice.tasks.permutation import save_and_permute
from entityservice.utils import similarity_matrix_from_csv_bytes


@celery.task(base=TracedTask, ignore_result=True, args_as_tags=('project_id', 'run_id'))
def solver_task(similarity_scores_filename, project_id, run_id, dataset_sizes, parent_span):
    log = logger.bind(pid=project_id, run_id=run_id)
    mc = connect_to_object_store()
    solver_task.span.log_kv({'datasetSizes': dataset_sizes,
                             'filename': similarity_scores_filename})
    score_file = mc.get_object(config.MINIO_BUCKET, similarity_scores_filename)
    log.debug("Creating python sparse matrix from bytes data")
    candidate_pairs = anonlink.serialization.load_candidate_pairs(score_file)
    log.info("Calculating the optimal mapping from similarity matrix")

    groups = anonlink.solving.greedy_solve(candidate_pairs)

    log.info("Entity groups have been computed")

    res = {
        "groups": groups,
        "datasetSizes": dataset_sizes
    }
    save_and_permute.delay(res, project_id, run_id, solver_task.get_serialized_span())
