# Unified Agentic Annotation Backend

This is the authoritative FastAPI backend for image, video, document, and text annotation. Image and text tasks use the same LangGraph orchestration, capability discovery, validation, quality review, HITL, persistence, audit, and export lifecycle.

The original text implementation is integrated under `app/text_backend/`. The standalone `textannotation-backendv2.3` directory remains as the source implementation/reference, but it is not started as a second application.

## Architecture

```text
API
  -> existing LangGraph agentic pipeline
  -> planning and capability discovery
  -> image capabilities OR integrated text capabilities
  -> modality-aware validation and quality review
  -> common HITL, persistence, audit, and export
```

Image capabilities include YOLO26, Grounding DINO, Faster R-CNN, SAM2, Florence, and CLIP. Integrated text capabilities reuse the existing text backend services for document extraction, OCR, entity extraction, sentiment, text classification, and relation extraction.

## Requirements and setup

Python 3.11+ is supported. Install the unified dependency set from the repository root:

```powershell
cd backned-latest
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Configure the existing image backend environment in `.env`, including Firebase/Google credentials, storage settings, and any enabled model settings. For text model execution configure:

- `GOOGLE_CLOUD_PROJECT`
- `GOOGLE_CLOUD_LOCATION` or the existing Vertex location setting
- Google Application Default Credentials
- Tesseract on the host when OCR is required

Never commit credentials or model weights.

## Run the unified backend

Start only this backend:

```powershell
primary_projects_query_ms=72.19 project_count=3 request_id=df8daa8f-ead5-402f-816a-124f54129e47 secondary_queries=4 total_service_ms=2864.53
2026-10-06T09:52:51.039712Z [info     ] projects_list_timing           [app.api.routes_main] auth_ms=0.0 firestore_client_acq_ms=0.0 permissions_ms=0.0 project_count=3 request_id=df8daa8f-ead5-402f-816a-124f54129e47 serialization_ms=0.1 service_list_projects_ms=2876.75 total_ms=2876.85
2026-10-06T09:52:51.040714Z [info     ] request_complete               [app.main] duration_ms=3027 method=GET path=/api/v1/projects request_id=df8daa8f-ead5-402f-816a-124f54129e47 status=200
2026-10-06T09:52:51.440759Z [info     ] quality_timing_assets          [app.services.quality_validation] count=50 elapsed_ms=129.77 request_id=87944c97-8f04-4b59-b36a-8601195b2f05
2026-10-06T09:52:55.647505Z [info     ] asset_read                     [app.api.routes_main] count=50 project_id=7facdfaf-eb1d-49fb-83fd-2dabd7980d17 request_id=c2603a37-d07d-4d8c-a194-fc7624ed724b
2026-10-06T09:52:55.649789Z [info     ] request_complete               [app.main] duration_ms=4582 method=GET path=/api/v1/projects/7facdfaf-eb1d-49fb-83fd-2dabd7980d17/assets request_id=c2603a37-d07d-4d8c-a194-fc7624ed724b status=200
2026-10-06T09:52:56.493430Z [info     ] quality_timing_annotations     [app.services.quality_validation] count=1769 elapsed_ms=5051.89 request_id=87944c97-8f04-4b59-b36a-8601195b2f05
2026-10-06T09:52:56.607476Z [info     ] quality_timing_decisions       [app.services.quality_validation] count=0 elapsed_ms=114.13 request_id=87944c97-8f04-4b59-b36a-8601195b2f05
2026-10-06T09:52:56.835589Z [info     ] quality_timing_deltas_audits   [app.services.quality_validation] audits=50 deltas=0 elapsed_ms=227.72 request_id=87944c97-8f04-4b59-b36a-8601195b2f05
2026-10-06T09:52:56.837605Z [info     ] calculate_project_quality_report_TOTAL [app.services.quality_validation] elapsed_ms=5611.5 request_id=87944c97-8f04-4b59-b36a-8601195b2f05
2026-10-06T09:52:56.850405Z [info     ] request_complete               [app.main] duration_ms=5785 method=GET path=/api/v1/projects/7facdfaf-eb1d-49fb-83fd-2dabd7980d17/quality-report request_id=87944c97-8f04-4b59-b36a-8601195b2f05 status=200
2026-10-06T09:52:57.000001Z [info     ] request_complete               [app.main] duration_ms=5935 method=GET path=/api/v1/projects/7facdfaf-eb1d-49fb-83fd-2dabd7980d17/production-dashboard request_id=22c57b03-3ebc-4e08-be3a-b0e45386934f status=200
2026-10-06T09:53:10.966356Z [info     ] projects_service_timing        [app.services.projects] annotation_count=2213 asset_count=71 firestore_document_reads=2287 firestore_queries=5 per_project_enrichment_ms=2916.9 primary_projects_query_ms=66.11 project_count=3 request_id=3b78714e-73de-417e-b5b5-fc9d0bfd6d27 secondary_queries=4 total_service_ms=2983.11
2026-10-06T09:53:10.979945Z [info     ] projects_list_timing           [app.api.routes_main] auth_ms=0.0 firestore_client_acq_ms=0.0 permissions_ms=0.0 project_count=3 request_id=3b78714e-73de-417e-b5b5-fc9d0bfd6d27 serialization_ms=0.1 service_list_projects_ms=2996.26 total_ms=2996.36
2026-10-06T09:53:10.980945Z [info     ] request_complete               [app.main] duration_ms=3173 method=GET path=/api/v1/projects request_id=3b78714e-73de-417e-b5b5-fc9d0bfd6d27 status=200
2026-10-06T09:53:13.968251Z [info     ] projects_service_timing        [app.services.projects] annotation_count=2213 asset_count=71 firestore_document_reads=2287 firestore_queries=5 per_project_enrichment_ms=2695.46 primary_projects_query_ms=100.0 project_count=3 request_id=47c10f29-feb2-46b4-a9ad-6556fc4436d9 secondary_queries=4 total_service_ms=2795.8
2026-10-06T09:53:13.984290Z [info     ] projects_list_timing           [app.api.routes_main] auth_ms=0.0 firestore_client_acq_ms=0.0 permissions_ms=0.0 project_count=3 request_id=47c10f29-feb2-46b4-a9ad-6556fc4436d9 serialization_ms=0.15 service_list_projects_ms=2812.22 total_ms=2812.38
2026-10-06T09:53:13.986293Z [info     ] request_complete               [app.main] duration_ms=2998 method=GET path=/api/v1/projects request_id=47c10f29-feb2-46b4-a9ad-6556fc4436d9 status=200
2026-10-06T09:53:17.393456Z [info     ] projects_service_timing        [app.services.projects] annotation_count=2213 asset_count=71 firestore_document_reads=2287 firestore_queries=5 per_project_enrichment_ms=3151.75 primary_projects_query_ms=76.33 project_count=3 request_id=de135073-b2a1-4533-9de0-62857063948e secondary_queries=4 total_service_ms=3228.32
2026-10-06T09:53:17.412205Z [info     ] projects_list_timing           [app.api.routes_main] auth_ms=0.0 firestore_client_acq_ms=0.0 permissions_ms=0.0 project_count=3 request_id=de135073-b2a1-4533-9de0-62857063948e serialization_ms=0.17 service_list_projects_ms=3247.35 total_ms=3247.53
2026-10-06T09:53:17.414203Z [info     ] request_complete               [app.main] duration_ms=3421 method=GET path=/api/v1/projects request_id=de135073-b2a1-4533-9de0-62857063948e status=200
2026-10-06T09:53:20.980907Z [info     ] projects_service_timing        [app.services.projects] annotation_count=2213 asset_count=71 firestore_document_reads=2287 firestore_queries=5 per_project_enrichment_ms=3323.14 primary_projects_query_ms=84.22 project_count=3 request_id=3757b1d2-5076-4097-a1ae-52bdf365f066 secondary_queries=4 total_service_ms=3407.47
2026-10-06T09:53:20.995443Z [info     ] projects_list_timing           [app.api.routes_main] auth_ms=0.0 firestore_client_acq_ms=0.0 permissions_ms=0.0 project_count=3 request_id=3757b1d2-5076-4097-a1ae-52bdf365f066 serialization_ms=0.12 service_list_projects_ms=3421.74 total_ms=3421.87
2026-10-06T09:53:20.996442Z [info     ] request_complete               [app.main] duration_ms=3576 method=GET path=/api/v1/projects request_id=3757b1d2-5076-4097-a1ae-52bdf365f066 status=200
2026-10-06T09:53:24.182845Z [info     ] projects_service_timing        [app.services.projects] annotation_count=2213 asset_count=71 firestore_document_reads=2287 firestore_queries=5 per_project_enrichment_ms=2941.05 primary_projects_query_ms=77.24 project_count=3 request_id=69e22ca7-188d-4f29-9f18-f95498228d31 secondary_queries=4 total_service_ms=3018.62
2026-10-06T09:53:24.200699Z [info     ] projects_list_timing           [app.api.routes_main] auth_ms=0.0 firestore_client_acq_ms=0.0 permissions_ms=0.0 project_count=3 request_id=69e22ca7-188d-4f29-9f18-f95498228d31 serialization_ms=0.09 service_list_projects_ms=3036.03 total_ms=3036.12
2026-10-06T09:53:24.201700Z [info     ] request_complete               [app.main] duration_ms=3197 method=GET path=/api/v1/projects request_id=69e22ca7-188d-4f29-9f18-f95498228d31 status=200
2026-10-06T09:53:27.509041Z [info     ] projects_service_timing        [app.services.projects] annotation_count=2213 asset_count=71 firestore_document_reads=2287 firestore_queries=5 per_project_enrichment_ms=3028.79 primary_projects_query_ms=80.84 project_count=3 request_id=a448ca1a-7a1c-471b-bb3f-4cd48399e4c6 secondary_queries=4 total_service_ms=3109.72
2026-10-06T09:53:27.523037Z [info     ] projects_list_timing           [app.api.routes_main] auth_ms=0.0 firestore_client_acq_ms=0.0 permissions_ms=0.0 project_count=3 request_id=a448ca1a-7a1c-471b-bb3f-4cd48399e4c6 serialization_ms=0.11 service_list_projects_ms=3123.24 total_ms=3123.35
2026-10-06T09:53:27.524047Z [info     ] request_complete               [app.main] duration_ms=3317 method=GET path=/api/v1/projects request_id=a448ca1a-7a1c-471b-bb3f-4cd48399e4c6 status=200
2026-10-06T09:53:31.898862Z [info     ] projects_service_timing        [app.services.projects] annotation_count=2213 asset_count=71 firestore_document_reads=2287 firestore_queries=5 per_project_enrichment_ms=4085.15 primary_projects_query_ms=98.65 project_count=3 request_id=a13cac82-b479-4825-86d8-d80c098131c3 secondary_queries=4 total_service_ms=4184.14
2026-10-06T09:53:31.910185Z [info     ] projects_list_timing           [app.api.routes_main] auth_ms=0.0 firestore_client_acq_ms=0.0 permissions_ms=0.0 project_count=3 request_id=a13cac82-b479-4825-86d8-d80c098131c3 serialization_ms=0.08 service_list_projects_ms=4194.87 total_ms=4194.96
2026-10-06T09:53:31.910750Z [info     ] request_complete               [app.main] duration_ms=4380 method=GET path=/api/v1/projects request_id=a13cac82-b479-4825-86d8-d80c098131c3 status=200
2026-10-06T09:53:35.627828Z [info     ] projects_service_timing        [app.services.projects] annotation_count=2213 asset_count=71 firestore_document_reads=2287 firestore_queries=5 per_project_enrichment_ms=3475.33 primary_projects_query_ms=81.29 project_count=3 request_id=1617cd1f-5535-40d1-be3d-8b584dd41084 secondary_queries=4 total_service_ms=3556.84
2026-10-06T09:53:35.639370Z [info     ] projects_list_timing           [app.api.routes_main] auth_ms=0.0 firestore_client_acq_ms=0.0 permissions_ms=0.0 project_count=3 request_id=1617cd1f-5535-40d1-be3d-8b584dd41084 serialization_ms=0.14 service_list_projects_ms=3568.33 total_ms=3568.46
2026-10-06T09:53:35.640367Z [info     ] request_complete               [app.main] duration_ms=3723 method=GET path=/api/v1/projects request_id=1617cd1f-5535-40d1-be3d-8b584dd41084 status=200
2026-10-06T09:53:36.017376Z [info     ] quality_timing_assets          [app.services.quality_validation] count=50 elapsed_ms=112.29 request_id=d07228e0-22ac-482f-8833-c4b0140dd649

```

Health endpoint:

```text
GET http://127.0.0.1:8000/api/v1/health
```

The frontend should proxy to `127.0.0.1:8000`. Do not start the old text backend separately on another port.

## Main APIs

Existing image/project APIs remain under `/api/v1`.

The compatible unified text endpoint is:

```text
POST /api/v1/text-annotation/analyze
```

Multipart fields:

- `project_id` and `asset_id`
- `analysis_type`: `ENTITY_EXTRACTION`, `SENTIMENT_ANALYSIS`, `TEXT_CLASSIFICATION`, or `RELATION_EXTRACTION`
- `assessment_name`
- `text` or uploaded `files`
- `identification_name` for entity extraction

Supported document types are PDF, DOCX, TXT, JPG, JPEG, and PNG when the required extraction/OCR dependencies are installed.

## Tests

Run the full test suite without loading heavyweight image models when appropriate:

```powershell
$env:SKIP_MODEL_LOAD = "true"
pytest -q
```

Targeted agentic regression tests:

```powershell
pytest -q app/agent/graphs app/inference
```

## Image models and MCP

- `app/agent/graphs/` contains the LangGraph orchestration.
- `app/agent/capability_registry.py` contains shared image and text capability descriptors.
- `app/inference/` owns image model lifecycle and adapters.
- `app/mcp/` contains MCP tools and servers for detection, segmentation, tracking, and verification.
- Model weights belong in the configured ignored cache and must not be committed.
