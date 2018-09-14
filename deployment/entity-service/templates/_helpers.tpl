{{/*
Expand the name of the chart.
*/}}
{{- define "name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
*/}}
{{- define "es.fullname" -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a fully qualified api server name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
*/}}
{{- define "api.fullname" -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- printf "%s-%s-%s" .Release.Name $name .Values.api.name | trunc 63 | trimSuffix "-" -}}
{{- end -}}


{{/*
We define the release labels that will be applied to all deployments.
*/}}
{{- define "es.release_labels" }}
app: {{ template "fullname" . }}
chart: {{ .Chart.Name }}-{{ .Chart.Version }}
# The "heritage" label is used to track which tool deployed a given chart.
# It is useful for admins who want to see what releases a particular tool
# is responsible for.
heritage: {{ .Release.Service }}
version: {{ .Chart.Version }}
# The "release" convention makes it easy to tie a release to all of the
# Kubernetes resources that were created as part of that release.
release: {{ .Release.Name }}
{{- end }}