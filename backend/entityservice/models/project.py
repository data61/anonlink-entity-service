from structlog import get_logger

from entityservice.messages import INVALID_RESULT_TYPE_MESSAGE
from entityservice.utils import generate_code
import entityservice.database as db

logger = get_logger()


class InvalidProjectParametersException(ValueError):

    def __init__(self, message, *args, **kwargs):
        self.msg = message
        super(*args, **kwargs)


class Project(object):
    """
    A python object representing a project.

    Exists before insertion into the database.
    """
    def __init__(self, result_type, schema, name, notes, parties, uses_blocking):
        logger.debug("Creating project codes")
        self.result_type = result_type
        self.schema = schema
        self.name = name
        self.notes = notes
        self.number_parties = parties
        self.uses_blocking = uses_blocking

        self.project_id = generate_code()
        logger.debug("Generated project code", pid=self.project_id)
        self.result_token = generate_code()

        # Order is important here
        self.update_tokens = [generate_code() for _ in range(parties)]

    VALID_RESULT_TYPES = {'groups',
                          'permutations',
                          'similarity_scores'}

    @staticmethod
    def from_json(data):
        if data is None or 'schema' not in data:
            raise InvalidProjectParametersException("Schema information required")

        if 'result_type' not in data or data['result_type'] not in Project.VALID_RESULT_TYPES:
            raise InvalidProjectParametersException(INVALID_RESULT_TYPE_MESSAGE)

        result_type = data['result_type']
        schema = data['schema']

        # Get optional fields from JSON data
        name = data.get('name', '')
        notes = data.get('notes', '')
        parties = int(data.get('number_parties', 2))
        uses_blocking = data.get('uses_blocking', False)

        if parties > 2 and result_type != 'groups':
            raise InvalidProjectParametersException(
                "Multi-party linkage requires result type 'groups'.")            
        if parties < 2:
            raise InvalidProjectParametersException("Record linkage requires at least 2 parties!")

        return Project(result_type, schema, name, notes, parties, uses_blocking)

    def save(self, conn):
        with conn.cursor() as cur:
            logger.debug("Starting database transaction. Creating project.")
            project_id = db.insert_new_project(cur,
                                               self.result_type,
                                               self.schema,
                                               self.result_token,
                                               self.project_id,
                                               self.number_parties,
                                               self.name,
                                               self.notes,
                                               self.uses_blocking
                                               )

            logger.debug("New project created in DB")
            logger.debug("Creating new data provider entries")

            dp_ids = []
            for auth_token in self.update_tokens:
                dp_id = db.insert_dataprovider(cur, auth_token, project_id)
                dp_ids.append(dp_id)
                logger.debug("Added a dataprovider to db", dp_id=dp_id)

            logger.debug("Added data providers")

            logger.debug("Committing transaction")
            conn.commit()
        return dp_ids
