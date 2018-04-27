from entityservice import app
from entityservice.messages import INVALID_RESULT_TYPE_MESSAGE
from entityservice.utils import generate_code
from entityservice.serialization import check_public_key
import entityservice.database as db


class InvalidProjectParametersException(ValueError):

    def __init__(self, message, *args, **kwargs):
        self.msg = message
        super(*args, **kwargs)


class Project(object):
    """
    A python object representing a project.

    Exists before insertion into the database.
    """
    def __init__(self, result_type, schema, name, notes, parties, public_key=None, paillier_context=None):
        app.logger.info("Creating project codes")
        self.result_type = result_type
        self.schema = schema
        self.name = name
        self.notes = notes
        self.number_parties = parties
        self.public_key = public_key
        self.paillier_context = paillier_context

        self.project_id = generate_code()
        self.result_token = generate_code()

        # Order is important here
        self.update_tokens = [generate_code() for _ in range(parties)]

        # TODO DELETE?
        self.ready = False
        self.status = 'not ready'
        self.data = {}
        self.result = {}

    VALID_RESULT_TYPES = {'permutation', 'mapping', 'permutation_unencrypted_mask', 'similarity_scores'}

    @staticmethod
    def from_json(data):
        if data is None or 'schema' not in data:
            raise InvalidProjectParametersException("Schema information required")

        if 'result_type' not in data or data['result_type'] not in Project.VALID_RESULT_TYPES:
            raise InvalidProjectParametersException(INVALID_RESULT_TYPE_MESSAGE)

        if data['result_type'] == 'permutation' and 'public_key' not in data:
            raise InvalidProjectParametersException('Paillier public key required when result_type="permutation"')

        if data['result_type'] == 'permutation' and 'paillier_context' not in data:
            raise InvalidProjectParametersException('Paillier context required when result_type="permutation"')

        if data['result_type'] == 'permutation' and not check_public_key(data['public_key']):
            raise InvalidProjectParametersException('Paillier public key required when result_type="permutation"')

        result_type = data['result_type']
        schema = data['schema']

        # Get optional fields from JSON data
        name = data.get('name', '')
        notes = data.get('notes', '')
        parties = data.get('parties', 2)

        return Project(result_type, schema, name, notes, parties)

    def save(self, conn):
        with conn.cursor() as cur:
            app.logger.debug("Starting database transaction. Creating project.")
            project_id = db.insert_new_project(cur,
                                               self.result_type,
                                               self.schema,
                                               self.result_token,
                                               self.project_id,
                                               self.number_parties,
                                               self.name,
                                               self.notes
                                               )

            if self.result_type == 'permutation':
                app.logger.debug("Inserting public key and paillier context into db")
                paillier_db_id = db.insert_paillier(cur, self.public_key, self.paillier_context)
                # TODO: have paillier context to be associated with a project not a run?
                #db.insert_empty_encrypted_mask(cur, project_id, paillier_db_id)

            app.logger.debug("New project created in DB: {}".format(project_id))
            app.logger.debug("Creating new data provider entries")

            for auth_token in self.update_tokens:
                dp_id = db.insert_dataprovider(cur, auth_token, project_id)
                app.logger.info("Added dataprovider with id = {}".format(dp_id))

            app.logger.debug("Added data providers")

            app.logger.debug("Committing transaction")
            conn.commit()

