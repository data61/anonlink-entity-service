from entityservice.database.util import query_db, execute_returning_id, logger
from entityservice.database.selections import get_project


def delete_project(db, resource_id):
    project = get_project(db, resource_id)
    project_id = project['project_id']
    result_type = project['result_type']

    raise NotImplemented("DELETE NEEDS WORK")
    # with db.cursor() as cur:
    #     logger.info("Beginning db transaction to remove a full project resource")
    #     dps = query_db(db, """
    #         SELECT id
    #         FROM dataproviders
    #         WHERE project = %s
    #         """, [project_id])
    #
    #     for dp in dps:
    #         cur.execute("""
    #             DELETE FROM bloomingdata
    #             WHERE dp = %s
    #             """, [dp['id']])
    #
    #         if result_type != 'mapping':
    #             cur.execute("""
    #                 DELETE FROM permutations
    #                 WHERE dp = %s
    #                 """, [dp['id']])
    #     if result_type != 'mapping':
    #         cur.execute("""
    #             DELETE FROM permutation_masks
    #             WHERE mapping = %s
    #             """, [resource_id])
    #
    #     if result_type == "permutation":
    #         paillier_id = execute_returning_id(cur, """
    #             DELETE FROM encrypted_permutation_masks
    #             WHERE mapping = %s
    #             RETURNING paillier
    #             """, [resource_id])
    #
    #         cur.execute("""
    #             DELETE FROM paillier
    #             WHERE id = %s
    #             """, [paillier_id])
    #
    #     if result_type == "similarity_scores":
    #         cur.execute("""
    #             DELETE FROM similarity_scores
    #             WHERE mapping = %s
    #             """, [resource_id])
    #
    #     cur.execute("""
    #         DELETE FROM dataproviders
    #         WHERE project = %s
    #         """, [project_id])
    #
    #     cur.execute("""
    #         DELETE FROM mapping_results
    #         WHERE mapping = %s
    #         """, [resource_id])
    #
    #     cur.execute("""
    #         DELETE FROM mappings
    #         WHERE resource_id = %s
    #         """, [resource_id])
    #
    # logger.info("Committing removal of mapping resource")
    # db.commit()