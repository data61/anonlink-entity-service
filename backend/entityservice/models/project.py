from entityservice import app
from entityservice.utils import generate_code


class Project(object):
    """
    A python object for a newly created mapping.

    Exists before insertion into the database.
    """
    def __init__(self, resource_id, parties=2):
        app.logger.info("Creating project codes")
        self.parties = parties
        self.project_id = resource_id
        self.result_token = generate_code()

        # Order is important here
        self.update_tokens = [generate_code() for _ in range(parties)]

        self.ready = False

        # These field will not be sent in the response
        self.status = 'not ready'
        self.data = {}

        self.result = {}