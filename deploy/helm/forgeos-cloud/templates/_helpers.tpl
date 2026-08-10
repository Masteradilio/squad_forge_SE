{{/*
Expand the name of the chart.
*/}}
{{- define "forgeos-cloud.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/* Selector labels shared by every chart workload and Service. */}}
{{- define "forgeos-cloud.selectorLabels" -}}
app.kubernetes.io/name: {{ include "forgeos-cloud.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/* Common labels for managed objects. */}}
{{- define "forgeos-cloud.labels" -}}
helm.sh/chart: {{ include "forgeos-cloud.name" . }}-{{ .Chart.Version | replace "+" "_" }}
{{ include "forgeos-cloud.selectorLabels" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/* Select the chart ServiceAccount without inventing a cluster-wide identity. */}}
{{- define "forgeos-cloud.serviceAccountName" -}}
{{- if .Values.serviceAccount.name }}
{{- .Values.serviceAccount.name }}
{{- else }}
{{- include "forgeos-cloud.fullname" . }}
{{- end }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "forgeos-cloud.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}
