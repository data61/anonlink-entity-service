Few helm tips:

To check if the provided values are sufficient, remove/delete the `Charts` folder and run:
```bash
helm lint -f values.yaml -f extraValues.yaml
```
It should return some information if some values are missing, e.g.
```bash
2019/09/11 15:13:10 [INFO] Missing required value: global.postgresql.postgresqlPassword must be provided.
2019/09/11 15:13:10 [INFO] Missing required value: minio.accessKey must be provided.
2019/09/11 15:13:10 [INFO] Missing required value: minio.secretKey must be provided.
==> Linting .
Lint OK

1 chart(s) linted, no failures
```

Notes:
 - it does not exit with a non 0 exit code, and our templates are currently failing if linting with the option `--strict`.
 - if the folder `Charts` is not deleted, the linting may throw some errors from the dependency charts if a
  value is missing, the error being slightly not descriptive, e.g. if the redis password is missing:
 ```bash
 ==> Linting .
[ERROR] templates/: render error in "entity-service/charts/redis-ha/templates/redis-auth-secret.yaml": template: entity-service/charts/redis-ha/templates/redis-auth-secret.yaml:10:35: executing "entity-service/charts/redis-ha/templates/redis-auth-secret.yaml" at <b64enc>: invalid value; expected string

Error: 1 chart(s) linted, 1 chart(s) failed
```

Then, it advised to use the `--dry-run` option before installing the template with `helm`.