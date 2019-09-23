
class InvalidConfiguration(ValueError):
    """Config wasn't as expected"""


class InactiveRun(AssertionError):
    pass


class DatabaseInconsistent(Exception):
    pass


class DBResourceMissing(DatabaseInconsistent):
    resource_type = 'unknown'

    def __init__(self, resource_id):
        msg = f"{self.resource_type} {resource_id} not found in database"
        super().__init__(msg)


class ProjectDeleted(DBResourceMissing):
    """The database is missing data that indicates the project has been deleted"""
    resource_type = 'project'


class RunDeleted(DBResourceMissing):
    """The database is missing data that indicates the a run has been deleted"""
    resource_type = 'run'


class DataProviderDeleted(DBResourceMissing):
    """The database is missing data that indicates that a data provider has been deleted"""
    resource_type = 'dataprovider'
