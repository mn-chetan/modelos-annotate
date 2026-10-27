from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, File, Form, Request, UploadFile
from pymongo.errors import DuplicateKeyError

from app.core.config import AnalysisType
from app.core.exceptions import AppError
from app.schemas.analysis import (
    AnalysisCreateResponse,
    AnalysisRecord,
    AnalysisResultItem,
    AssessmentLookupItem,
    HumanReviewSubmitRequest,
    QCReviewSubmitRequest,
    WorkflowAuditEvent,
    WorkflowSummary,
)
from app.services.text_extraction_service import TextExtractionService
from app.services.drug_matching_service import DrugMatchingService
from app.services.sentiment_service import SentimentService
from app.services.relation_extraction_service import RelationExtractionService
from app.services.text_classification_service import TextClassificationService
from app.repositories.analysis_repository import AnalysisRepository
from app.repositories.source_repository import SourceRepository

router = APIRouter(
    prefix="/api/v1/annotations",
    tags=["annotations"],
)


def _services(
    request: Request,
) -> tuple[
    TextExtractionService,
    DrugMatchingService,
    SentimentService,
    RelationExtractionService,
    TextClassificationService,
    SourceRepository,
    AnalysisRepository,
]:
    state = request.app.state
    return (
        state.text_extraction_service,
        state.drug_matching_service,
        state.sentiment_service,
        state.relation_extraction_service,
        state.text_classification_service,
        state.source_repository,
        state.analysis_repository,
    )


def _confidence_score(result: dict[str, Any]) -> float | None:
    if "confidence" in result and isinstance(result["confidence"], (float, int)):
        return float(result["confidence"])

    entities = result.get("entities")
    if isinstance(entities, list) and entities:
        scores = [
            float(entity["confidence_score"])
            for entity in entities
            if isinstance(entity, dict) and isinstance(entity.get("confidence_score"), (float, int))
        ]
        if scores:
            return sum(scores) / len(scores)

    return None


def _workflow_summary(document: dict[str, Any]) -> WorkflowSummary:
    return WorkflowSummary.model_validate(document)


def _require_role(request: Request, expected_role: str) -> str:
    role = request.headers.get("X-Reviewer-Role")
    reviewer_name = request.headers.get("X-Reviewer-Name", "")

    if role != expected_role:
        raise AppError(
            "FORBIDDEN",
            f"This action requires the {expected_role} role.",
            status_code=403,
        )

    if not reviewer_name.strip():
        raise AppError(
            "REVIEWER_NAME_REQUIRED",
            "X-Reviewer-Name is required.",
            status_code=422,
        )

    return reviewer_name


@router.post(
    "/analyze",
    response_model=AnalysisCreateResponse,
)
async def analyze(
    request: Request,
    analysis_type: AnalysisType = Form(...),
    text: str | None = Form(None),
    assessment_name: str | None = Form(None),
    identification_name: str | None = Form(None),
    files: list[UploadFile] | None = File(None),
):
    (
        text_extraction_service,
        drug_matching_service,
        sentiment_service,
        relation_extraction_service,
        text_classification_service,
        source_repository,
        analysis_repository,
    ) = _services(request)

    has_text = bool(text and text.strip())
    file_uploads = files or []

    has_file = bool(file_uploads)

    if not assessment_name:
        raise AppError(
            "ASSESSMENT_NAME_REQUIRED",
            "assessment_name is required.",
            status_code=422,
        )

    if (
        analysis_type == "ENTITY_EXTRACTION"
        and not (identification_name and identification_name.strip())
    ):
        raise AppError(
            "IDENTIFICATION_NAME_REQUIRED",
            "identification_name is required for entity extraction.",
            status_code=422,
        )

    if not has_text and not has_file:
        raise AppError(
            "INPUT_REQUIRED",
            "Provide either text or files.",
            status_code=422,
        )

    if has_text and has_file:
        raise AppError(
            "INPUT_CONFLICT",
            "Provide either text or files, not both.",
            status_code=422,
        )

    existing_assessment = await analysis_repository.find_by_assessment_name(assessment_name)
    if existing_assessment is not None:
        raise AppError(
            "ASSESSMENT_NAME_ALREADY_EXISTS",
            "assessment_name must be unique.",
            status_code=409,
        )

    if has_text:
        sources = [
            await text_extraction_service.extract_from_text(text)
        ]
    else:
        sources = []

        for upload_file in file_uploads:
            source = await text_extraction_service.extract_from_upload(
                upload_file
            )
            sources.append(source)

    results: list[AnalysisResultItem] = []
    source_ids: list[UUID] = []
    analysis_id = uuid4()
    created_at = datetime.utcnow()

    requested_entities = []

    if analysis_type == "ENTITY_EXTRACTION":
        requested_entities = [
            value.strip()
            for value in (identification_name or "")
            .replace("\n", ",")
            .split(",")
            if value.strip()
        ]

    for source in sources:
        source_ids.append(source.source_id)

        try:
            await source_repository.create(source)
        except Exception as exc:
            raise AppError(
                "MONGODB_FAILURE",
                "Failed to save source in MongoDB.",
                status_code=502,
            ) from exc

        if analysis_type == "ENTITY_EXTRACTION":

            result = await drug_matching_service.analyze(
                source,
                identification_name or "",
            )
            result_dict = result.model_dump()
            confidence_score = _confidence_score(result_dict)
            workflow_status = "HUMAN_REVIEW" if confidence_score is not None and confidence_score < 0.95 else "COMPLETED"

        elif analysis_type == "SENTIMENT_ANALYSIS":

            result = await sentiment_service.analyze(source)
            result_dict = result.model_dump()
            confidence_score = _confidence_score(result_dict)
            workflow_status = "HUMAN_REVIEW" if confidence_score is not None and confidence_score < 0.95 else "COMPLETED"

        elif analysis_type == "RELATION_EXTRACTION":

            result = await relation_extraction_service.analyze(source)
            result_dict = result.model_dump()
            confidence_score = _confidence_score(result_dict)
            workflow_status = "HUMAN_REVIEW" if confidence_score is not None and confidence_score < 0.95 else "COMPLETED"

        else:

            result = await text_classification_service.analyze(source)
            result_dict = result.model_dump()
            confidence_score = _confidence_score(result_dict)
            workflow_status = "HUMAN_REVIEW" if confidence_score is not None and confidence_score < 0.95 else "COMPLETED"

        source_url = None

        if source.original_filename:
            source_url = str(
                request.url_for(
                    "get_source",
                    source_id=str(source.source_id),
                )
            )

        human_review_url = str(
            request.url_for(
                "get_analysis_workflow",
                analysis_id=str(analysis_id),
            )
        )

        qc_review_url = str(
            request.url_for(
                "get_analysis_workflow",
                analysis_id=str(analysis_id),
            )
        )

        results.append(
            AnalysisResultItem(
                analysis_id=analysis_id,
                source_id=source.source_id,
                source_type=source.source_type,
                source_url=source_url,
                file_name=source.original_filename,
                original_text=source.extracted_text
                or source.text,
                confidence_threshold=(
                    request.app.state.settings.semantic_match_threshold
                    / 100
                ),
                confidence_score=confidence_score,
                status=workflow_status,
                result=result_dict,
                human_review_url=human_review_url if workflow_status == "HUMAN_REVIEW" else None,
                qc_review_url=qc_review_url if workflow_status == "COMPLETED" else None,
                created_at=created_at,
            )
        )

    overall_status = "HUMAN_REVIEW" if any(item.status == "HUMAN_REVIEW" for item in results) else "COMPLETED"
    confidence_scores = [item.confidence_score for item in results if item.confidence_score is not None]
    overall_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else None

    if len(results) == 1:
        overall_result: dict[str, Any] = results[0].result
    else:
        overall_result = {
            "analysis_type": analysis_type,
            "assessment_name": assessment_name,
            "source_count": len(results),
            "results": [
                {
                    "source_id": str(item.source_id),
                    "file_name": item.file_name,
                    "original_text": item.original_text,
                    "confidence_score": item.confidence_score,
                    "status": item.status,
                    "result": item.result,
                }
                for item in results
            ],
        }

    record = AnalysisRecord(
        analysis_id=analysis_id,
        source_id=source_ids[0],
        source_ids=source_ids,
        analysis_type=analysis_type,
        assessment_name=assessment_name,
        identification_name=requested_entities,
        model_name=request.app.state.settings.gemini_model if analysis_type != "ENTITY_EXTRACTION" else None,
        status=overall_status,
        confidence_score=overall_confidence,
        result=overall_result,
        results=results,
        created_at=created_at,
        updated_at=created_at,
        audit_trail=[
            WorkflowAuditEvent(
                action="ANALYSIS_CREATED",
                reviewer_name="system",
                reviewer_role="SYSTEM",
                status_after=overall_status,
                updated_fields=["result", "status"],
                comments="Initial analysis completed.",
            )
        ],
        versions=[],
    )

    try:
        await analysis_repository.create(record)
    except DuplicateKeyError as exc:
        raise AppError(
            "ASSESSMENT_NAME_ALREADY_EXISTS",
            "assessment_name must be unique.",
            status_code=409,
        ) from exc
    except Exception as exc:
        raise AppError(
            "MONGODB_FAILURE",
            "Failed to save analysis in MongoDB.",
            status_code=502,
        ) from exc

    return AnalysisCreateResponse(
        analysis_type=analysis_type,
        assessment_name=assessment_name,
        status=overall_status,
        results=results,
    )


@router.get("/qc-unapproved", response_model=list[AssessmentLookupItem])
async def get_unapproved_qc_assessments(request: Request):
    analysis_repository = request.app.state.analysis_repository
    documents = await analysis_repository.list_unapproved_qc_assessments()
    return [AssessmentLookupItem.model_validate(document) for document in documents]


@router.get("/{analysis_id}", response_model=WorkflowSummary, name="get_analysis_workflow")
async def get_analysis_workflow(request: Request, analysis_id: str):
    analysis_repository = request.app.state.analysis_repository
    document = await analysis_repository.find_by_analysis_id(analysis_id)
    if document is None:
        raise AppError("ANALYSIS_NOT_FOUND", "Analysis not found.", status_code=404)
    return _workflow_summary(document)


@router.post("/{analysis_id}/human-review", response_model=WorkflowSummary)
async def submit_human_review(
    request: Request,
    analysis_id: str,
    payload: HumanReviewSubmitRequest,
):
    analysis_repository = request.app.state.analysis_repository
    reviewer_name = _require_role(request, "HUMAN_REVIEWER")
    document = await analysis_repository.update_workflow(
        analysis_id,
        status="QC_VERIFICATION",
        updated_by=reviewer_name,
        reviewer_role="HUMAN_REVIEWER",
        result=payload.result,
        comments=payload.comments,
        updated_fields=["human_review_result", "status"],
        assigned_reviewer_role="QC_REVIEWER",
        assigned_reviewer_name=None,
    )
    if document is None:
        raise AppError("ANALYSIS_NOT_FOUND", "Analysis not found.", status_code=404)
    return _workflow_summary(document)


@router.post("/{analysis_id}/qc-review", response_model=WorkflowSummary)
async def submit_qc_review(
    request: Request,
    analysis_id: str,
    payload: QCReviewSubmitRequest,
):
    analysis_repository = request.app.state.analysis_repository
    reviewer_name = _require_role(request, "QC_REVIEWER")
    document = await analysis_repository.find_by_analysis_id(analysis_id)
    if document is None:
        raise AppError("ANALYSIS_NOT_FOUND", "Analysis not found.", status_code=404)

    if payload.approved:
        document = await analysis_repository.update_workflow(
            analysis_id,
            status="COMPLETED",
            updated_by=reviewer_name,
            reviewer_role="QC_REVIEWER",
            result=document.get("human_review_result") or document.get("result"),
            comments=payload.comments,
            approval_decision="APPROVED",
            updated_fields=["qc_result", "status"],
            preserve_human_review_result=True,
        )
        return _workflow_summary(document)

    if not payload.comments or not payload.comments.strip():
        raise AppError("QC_COMMENTS_REQUIRED", "QC comments are required when rejecting a record.", status_code=422)

    document = await analysis_repository.update_workflow(
        analysis_id,
        status="HUMAN_REVIEW",
        updated_by=reviewer_name,
        reviewer_role="QC_REVIEWER",
        result=document.get("human_review_result") or document.get("result"),
        comments=payload.comments,
        rejection_reason=payload.comments,
        updated_fields=["qc_result", "status"],
        preserve_human_review_result=True,
    )
    return _workflow_summary(document)