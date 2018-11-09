from marshmallow import Schema, fields


class ListSchema(Schema):
    def dump(self, obj, update_fields=True):
        return super().dump(obj, many=True, update_fields=update_fields)


class ProjectList(ListSchema):
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


class RunList(ListSchema):
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


class queued(RunStatus):
    time_started = fields.DateTime(format='iso8601', required=True)


class running(RunStatus):
    time_started = fields.DateTime(format='iso8601', required=True)


class error(RunStatus):
    message = fields.String(required=True)
    detail = fields.String()
