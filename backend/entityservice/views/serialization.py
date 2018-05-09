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
    public_key = fields.Raw()
    paillier_context = fields.Raw()


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
