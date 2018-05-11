from entityservice import app
from entityservice.utils import generate_code
import entityservice.database as db
from entityservice.settings import Config as config


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
        app.logger.info("Creating run id")
        self.run_id = generate_code()

    @staticmethod
    def from_json(data, project_id):
        # Get optional fields from JSON data
        threshold = data.get('threshold', config.ENTITY_MATCH_THRESHOLD)
        if threshold <= 0.0 or threshold > 1.0:
            raise InvalidRunParametersException("Threshold parameter out of range")
        app.logger.info("Threshold for run is: {}".format(threshold))

        name = data.get('name', '')
        notes = data.get('notes', '')

        return Run(project_id, threshold, name, notes)

    def save(self, conn):
        app.logger.debug("Saving run in database")
        db.insert_new_run(conn, self.run_id, self.project_id, self.threshold, self.name, self.notes)
        app.logger.debug("New run created in DB: {}".format(self.run_id))
