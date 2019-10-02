from structlog import get_logger

from entityservice.cache import progress as progress_cache
import entityservice.database as db
from entityservice.database import DBConn
from entityservice.utils import generate_code


logger = get_logger()

RUN_TYPES = {
    'default': {
        'stages': 3,
        'stage_descriptions': {
            1: 'waiting for CLKs',
            2: 'compute similarity scores',
            3: 'compute output'
        },
        'stage_progress_descriptions': {
            1: 'number of parties already contributed',
            2: 'number of already computed similarity scores'
        }
    },
    'no_mapping': {
        'stages': 2,
        'stage_descriptions': {
            1: 'waiting for CLKs',
            2: 'compute similarity scores'
        },
        'stage_progress_descriptions': {
            1: 'number of parties already contributed',
            2: 'number of already computed similarity scores'
        }
    }
}


def progress_run_stage(conn, run_id):
    log = logger.bind(run_id=run_id)
    log.info("Run progressing to next stage")
    db.progress_run_stage(conn, run_id)
    # clear progress in cache
    progress_cache.clear_progress(run_id)


class InvalidRunParametersException(ValueError):

    def __init__(self, message, *args, **kwargs):
        self.msg = message
        super(*args, **kwargs)


class Run(object):
    """
    A python object representing a run.

    """

    def __init__(self, project_id, threshold, name, notes):
        self.project_id = project_id
        self.name = name
        self.notes = notes
        self.threshold = threshold
        self.run_id = generate_code()
        logger.info("Created run id", rid=self.run_id)

        with DBConn() as conn:
            self.type = 'no_mapping' \
                if db.get_project_column(conn, project_id, 'result_type') == 'similarity_scores' \
                else 'default'

    @staticmethod
    def from_json(data, project_id):
        threshold = data['threshold']
        if threshold <= 0.0 or threshold > 1.0:
            raise InvalidRunParametersException("Threshold parameter out of range")
        logger.info("Threshold for run is: {}".format(threshold))

        # Get optional fields from JSON data
        name = data.get('name', '')
        notes = data.get('notes', '')

        return Run(project_id, threshold, name, notes)

    def save(self, conn):
        logger.debug("Saving run in database", rid=self.run_id)
        db.insert_new_run(db=conn, run_id=self.run_id, project_id=self.project_id, threshold=self.threshold,
                          name=self.name, notes=self.notes, type=self.type)
        logger.debug("New run created in DB", rid=self.run_id)
