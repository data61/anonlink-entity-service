from marshmallow import Schema, fields


class ProjectListItem(Schema):
    """
    serialize a list of projects by calling ProjectListItem(many=True).dump(projects)
    """
    project_id = fields.String()
    time_added = fields.DateTime(format='iso8601')


class ProjectDescription(Schema):
    project_id = fields.String()
    parties_contributed = fields.Integer()
    schema = fields.Raw(required=True)
    result_type = fields.String(required=True)
    number_parties = fields.Integer(attribute='parties')
    name = fields.String()
    notes = fields.String()
    error = fields.Boolean()
    uses_blocking = fields.Boolean()


class NewProjectResponse(Schema):
    project_id = fields.String()
    update_tokens = fields.List(fields.String)
    result_token = fields.String()


class NewRun(Schema):
    threshold = fields.Float(required=True)
    notes = fields.String()
    name = fields.String()


class RunDescription(NewRun):
    run_id = fields.String()


class RunListItem(Schema):
    run_id = fields.String()
    time_added = fields.DateTime(format='iso8601')
    state = fields.String()


class RunProgress(Schema):
    absolute = fields.Integer(required=True)
    description = fields.String()
    relative = fields.Float(required=True)


class RunStage(Schema):
    number = fields.Integer(required=True)
    description = fields.String()
    progress = fields.Nested(RunProgress)


class RunStatus(Schema):
    time_added = fields.DateTime(format='iso8601', required=True)
    state = fields.String(required=True)
    stages = fields.Integer(required=True)
    current_stage = fields.Nested(RunStage)


class completed(RunStatus):
    time_started = fields.DateTime(format='iso8601', required=True)
    time_completed = fields.DateTime(format='iso8601', required=True)
    total_number_comparisons = fields.Integer(required=True)


class queued(RunStatus):
    time_started = fields.DateTime(format='iso8601', required=True)


class running(RunStatus):
    time_started = fields.DateTime(format='iso8601', required=True)


class error(RunStatus):
    message = fields.String(required=True)
    detail = fields.String()


class ObjectStoreCredentials(Schema):
    access_key = fields.String(data_key="AccessKeyId")
    secret_key = fields.String(data_key="SecretAccessKey")
    session_token = fields.String(data_key="SessionToken")
    # Note expiry is from a separate object
    #expiry = fields.String(data_key="Expiration")
