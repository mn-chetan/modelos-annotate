from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

from app.schemas.analysis import AnalysisCreateResponse
from app.schemas.analysis import RelationExtractionAnalysisResult, RelationExtractionRelation
from app.schemas.entity import EntityAnalysisResult, EntityMatch
from app.schemas.sentiment import SentimentAnalysisResult
from app.schemas.source import SourceDocument


class FakeTextExtractionService:
    async def extract_from_text(self, text: str):
        return SourceDocument(source_type="TEXT", text=text, extracted_text=text)

    async def extract_from_upload(self, upload_file):
        content = await upload_file.read()
        text = content.decode("utf-8", errors="ignore")
        return SourceDocument(source_type="TXT", original_filename=upload_file.filename, extracted_text=text, text=text)


class FakeDrugMatchingService:
    async def analyze(self, source, identification_name: str):
        return EntityAnalysisResult(
            entities=[
                EntityMatch(
                    entity_name=name,
                    matched_text=name,
                    tag="PERSON" if " " in name else "TECHNOLOGY",
                    found=True,
                    confidence_score=0.98,
                )
                for name in [part.strip() for part in identification_name.split(",") if part.strip()]
            ],
        )


class FakeSentimentService:
    async def analyze(self, source):
        return SentimentAnalysisResult(sentiment="POSITIVE", confidence=0.94, reason="Positive", chunk_results=[])


class FakeTextClassificationService:
    async def analyze(self, source):
        from app.schemas.analysis import TextClassificationAnalysisResult

        return TextClassificationAnalysisResult(label="Login Issue", confidence=0.96, reason="Login failure", chunk_results=[])


class FakeRelationExtractionService:
    async def analyze(self, source):
        return RelationExtractionAnalysisResult(
            confidence=0.98,
            reason="Extracted relation from contract text.",
            relations=[
                RelationExtractionRelation(
                    source="John Smith",
                    relation="WORKS_FOR",
                    target="Tech Mahindra",
                    confidence=0.98,
                    reason="The text states John Smith joined Tech Mahindra.",
                ),
                RelationExtractionRelation(
                    source="John Smith",
                    relation="HAS_ROLE",
                    target="Senior Developer",
                    confidence=0.98,
                    reason="The text states John Smith joined as a Senior Developer.",
                ),
            ],
        )


class LowConfidenceDrugMatchingService:
    async def analyze(self, source, identification_name: str):
        return EntityAnalysisResult(
            entities=[
                EntityMatch(
                    entity_name=name,
                    matched_text=name,
                    tag="TECHNOLOGY",
                    found=True,
                    confidence_score=0.91,
                )
                for name in [part.strip() for part in identification_name.split(",") if part.strip()]
            ],
        )


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "mongodb": "connected"}


def test_direct_text_sentiment_request(client):
    client.app.state.text_extraction_service = FakeTextExtractionService()
    client.app.state.drug_matching_service = FakeDrugMatchingService()
    client.app.state.sentiment_service = FakeSentimentService()
    client.app.state.text_classification_service = FakeTextClassificationService()

    response = client.post(
        "/api/v1/annotations/analyze",
        data={"analysis_type": "SENTIMENT_ANALYSIS", "assessment_name": "Assessment-001", "text": "The medicine worked well for me."},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["analysis_type"] == "SENTIMENT_ANALYSIS"
    assert body["assessment_name"] == "Assessment-001"
    assert len(body["results"]) == 1
    assert body["results"][0]["original_text"] == "The medicine worked well for me."
    assert body["results"][0]["result"]["sentiment"] == "POSITIVE"


def test_relation_extraction_request(client):
    client.app.state.text_extraction_service = FakeTextExtractionService()
    client.app.state.drug_matching_service = FakeDrugMatchingService()
    client.app.state.sentiment_service = FakeSentimentService()
    client.app.state.text_classification_service = FakeTextClassificationService()
    client.app.state.relation_extraction_service = FakeRelationExtractionService()

    response = client.post(
        "/api/v1/annotations/analyze",
        data={"analysis_type": "RELATION_EXTRACTION", "assessment_name": "contract-relations"},
        files=[("files", ("contract.pdf", b"John Smith joined Tech Mahindra as a Senior Developer.", "application/pdf"))],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["analysis_type"] == "RELATION_EXTRACTION"
    assert body["results"][0]["result"]["relations"][0]["relation"] == "WORKS_FOR"
    assert body["results"][0]["result"]["relations"][1]["relation"] == "HAS_ROLE"


def test_entity_extraction_request(client):
    client.app.state.text_extraction_service = FakeTextExtractionService()
    client.app.state.drug_matching_service = FakeDrugMatchingService()
    client.app.state.sentiment_service = FakeSentimentService()
    client.app.state.text_classification_service = FakeTextClassificationService()

    response = client.post(
        "/api/v1/annotations/analyze",
        data={"analysis_type": "ENTITY_EXTRACTION", "text": "Abilash Vishnudoss is a Software Engineer.", "assessment_name": "Assessment-001", "identification_name": "Abilash Vishnudoss, Software Engineer, Python"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["analysis_type"] == "ENTITY_EXTRACTION"
    assert body["assessment_name"] == "Assessment-001"
    assert len(body["results"]) == 1
    assert body["results"][0]["original_text"] == "Abilash Vishnudoss is a Software Engineer."
    assert body["results"][0]["result"]["entities"][0]["entity_name"] == "Abilash Vishnudoss"
    assert body["results"][0]["result"]["entities"][0]["found"] is True


def test_entity_extraction_single_file_request(client):
    client.app.state.text_extraction_service = FakeTextExtractionService()
    client.app.state.drug_matching_service = FakeDrugMatchingService()
    client.app.state.sentiment_service = FakeSentimentService()
    client.app.state.text_classification_service = FakeTextClassificationService()

    response = client.post(
        "/api/v1/annotations/analyze",
        data={"analysis_type": "ENTITY_EXTRACTION", "assessment_name": "Assessment-002", "identification_name": "Abilash Vishnudoss, Python"},
        files=[("files", ("resume-1.txt", b"Abilash Vishnudoss works with Python.", "text/plain"))],
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["results"]) == 1
    assert body["results"][0]["source_url"] is not None
    assert body["results"][0]["file_name"] == "resume-1.txt"
    assert body["results"][0]["original_text"] == "Abilash Vishnudoss works with Python."


def test_entity_extraction_requires_assessment_name(client):
    client.app.state.text_extraction_service = FakeTextExtractionService()
    client.app.state.drug_matching_service = FakeDrugMatchingService()
    client.app.state.sentiment_service = FakeSentimentService()
    client.app.state.text_classification_service = FakeTextClassificationService()

    response = client.post(
        "/api/v1/annotations/analyze",
        data={"analysis_type": "ENTITY_EXTRACTION", "assessment_name": "Assessment-001"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "IDENTIFICATION_NAME_REQUIRED"


def test_mongo_failure_returns_structured_error(client, monkeypatch):
    client.app.state.text_extraction_service = FakeTextExtractionService()
    client.app.state.drug_matching_service = FakeDrugMatchingService()
    client.app.state.sentiment_service = FakeSentimentService()
    client.app.state.text_classification_service = FakeTextClassificationService()

    async def failing_insert(_):
        raise RuntimeError("db down")

    monkeypatch.setattr(client.app.state.source_repository, "create", failing_insert)

    response = client.post(
        "/api/v1/annotations/analyze",
        data={"analysis_type": "SENTIMENT_ANALYSIS", "assessment_name": "Assessment-002", "text": "The medicine worked well."},
    )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "MONGODB_FAILURE"


def test_source_lookup_returns_original_text(client):
    client.app.state.text_extraction_service = FakeTextExtractionService()
    client.app.state.drug_matching_service = FakeDrugMatchingService()
    client.app.state.sentiment_service = FakeSentimentService()
    client.app.state.text_classification_service = FakeTextClassificationService()

    response = client.post(
        "/api/v1/annotations/analyze",
        data={"analysis_type": "SENTIMENT_ANALYSIS", "assessment_name": "Assessment-003"},
        files=[("files", ("notes.txt", b"The medicine worked well.", "text/plain"))],
    )
    assert response.status_code == 200
    item = response.json()["results"][0]
    assert item["source_url"] is not None

    source_response = client.get(item["source_url"].replace("http://testserver", ""))
    assert source_response.status_code == 200
    assert source_response.json()["extracted_text"] == "The medicine worked well."


def test_low_confidence_entity_extraction_enters_review_cycle(client):
    client.app.state.text_extraction_service = FakeTextExtractionService()
    client.app.state.drug_matching_service = LowConfidenceDrugMatchingService()
    client.app.state.sentiment_service = FakeSentimentService()
    client.app.state.text_classification_service = FakeTextClassificationService()

    response = client.post(
        "/api/v1/annotations/analyze",
        data={"analysis_type": "ENTITY_EXTRACTION", "assessment_name": "Assessment-005", "identification_name": "Abilash Vishnudoss, Python"},
        files=[("files", ("resume-2.txt", b"Abilash Vishnudoss works with Python.", "text/plain"))],
    )
    assert response.status_code == 200
    item = response.json()["results"][0]
    assert item["status"] == "HUMAN_REVIEW"
    assert item["human_review_url"] is not None

    analysis_id = item["analysis_id"]
    human_review_response = client.post(
        f"/api/v1/annotations/{analysis_id}/human-review",
        headers={"X-Reviewer-Role": "HUMAN_REVIEWER", "X-Reviewer-Name": "Alice Reviewer"},
        json={"reviewer_name": "Alice Reviewer", "result": {"entities": [{"entity_name": "Abilash Vishnudoss", "matched_text": "Abilash Vishnudoss", "tag": "PERSON", "found": True, "confidence_score": 0.99}]}, "comments": "Corrected entity tag."},
    )
    assert human_review_response.status_code == 200
    assert human_review_response.json()["status"] == "QC_VERIFICATION"

    qc_reject_response = client.post(
        f"/api/v1/annotations/{analysis_id}/qc-review",
        headers={"X-Reviewer-Role": "QC_REVIEWER", "X-Reviewer-Name": "Bob QC"},
        json={"reviewer_name": "Bob QC", "approved": False, "comments": "Update the entity confidence and tag."},
    )
    assert qc_reject_response.status_code == 200
    assert qc_reject_response.json()["status"] == "HUMAN_REVIEW"

    qc_reject_missing_comments = client.post(
        f"/api/v1/annotations/{analysis_id}/qc-review",
        headers={"X-Reviewer-Role": "QC_REVIEWER", "X-Reviewer-Name": "Bob QC"},
        json={"reviewer_name": "Bob QC", "approved": False, "comments": ""},
    )
    assert qc_reject_missing_comments.status_code == 422
    assert qc_reject_missing_comments.json()["error"]["code"] == "QC_COMMENTS_REQUIRED"

    final_human_review_response = client.post(
        f"/api/v1/annotations/{analysis_id}/human-review",
        headers={"X-Reviewer-Role": "HUMAN_REVIEWER", "X-Reviewer-Name": "Alice Reviewer"},
        json={"reviewer_name": "Alice Reviewer", "result": {"entities": [{"entity_name": "Abilash Vishnudoss", "matched_text": "Abilash Vishnudoss", "tag": "PERSON", "found": True, "confidence_score": 0.99}]}, "comments": "Applied QC feedback."},
    )
    assert final_human_review_response.status_code == 200

    qc_approve_response = client.post(
        f"/api/v1/annotations/{analysis_id}/qc-review",
        headers={"X-Reviewer-Role": "QC_REVIEWER", "X-Reviewer-Name": "Bob QC"},
        json={"reviewer_name": "Bob QC", "approved": True, "comments": "Approved."},
    )
    assert qc_approve_response.status_code == 200
    assert qc_approve_response.json()["status"] == "COMPLETED"


def test_text_classification_request(client):
    client.app.state.text_extraction_service = FakeTextExtractionService()
    client.app.state.drug_matching_service = FakeDrugMatchingService()
    client.app.state.sentiment_service = FakeSentimentService()
    client.app.state.text_classification_service = FakeTextClassificationService()

    response = client.post(
        "/api/v1/annotations/analyze",
        data={"analysis_type": "TEXT_CLASSIFICATION", "assessment_name": "Assessment-006", "text": "Unable to login after password reset."},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["analysis_type"] == "TEXT_CLASSIFICATION"
    assert body["results"][0]["result"]["label"] == "Login Issue"


def test_multiple_file_upload_creates_single_analysis_record(client):
    client.app.state.text_extraction_service = FakeTextExtractionService()
    client.app.state.drug_matching_service = FakeDrugMatchingService()
    client.app.state.sentiment_service = FakeSentimentService()
    client.app.state.text_classification_service = FakeTextClassificationService()

    response = client.post(
        "/api/v1/annotations/analyze",
        data={"analysis_type": "TEXT_CLASSIFICATION", "assessment_name": "multiple-part-upload"},
        files=[
            ("files", ("part-1.pdf", b"Unable to login after password reset.", "application/pdf")),
            ("files", ("part-2.pdf", b"Payment deducted but order not created.", "application/pdf")),
        ],
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["results"]) == 2
    assert len(client.app.state.fake_db["analyses"].documents) == 1
    stored = client.app.state.fake_db["analyses"].documents[0]
    assert stored["assessment_name"] == "multiple-part-upload"
    assert len(stored["results"]) == 2
    assert len(stored["source_ids"]) == 2


def test_duplicate_assessment_name_is_rejected(client):
    client.app.state.text_extraction_service = FakeTextExtractionService()
    client.app.state.drug_matching_service = FakeDrugMatchingService()
    client.app.state.sentiment_service = FakeSentimentService()
    client.app.state.text_classification_service = FakeTextClassificationService()

    first = client.post(
        "/api/v1/annotations/analyze",
        data={"analysis_type": "TEXT_CLASSIFICATION", "assessment_name": "duplicate-assessment", "text": "Unable to login after password reset."},
    )
    assert first.status_code == 200

    second = client.post(
        "/api/v1/annotations/analyze",
        data={"analysis_type": "TEXT_CLASSIFICATION", "assessment_name": "duplicate-assessment", "text": "Payment deducted but order not created."},
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "ASSESSMENT_NAME_ALREADY_EXISTS"


def test_get_unapproved_qc_assessments_returns_assessment_names_and_ids(client):
    analyses = client.app.state.fake_db["analyses"].documents
    analyses.extend(
        [
            {
                "analysis_id": "11111111-1111-1111-1111-111111111111",
                "assessment_name": "pending-assessment",
                "status": "HUMAN_REVIEW",
            },
            {
                "analysis_id": "22222222-2222-2222-2222-222222222222",
                "assessment_name": "approved-assessment",
                "status": "COMPLETED",
            },
            {
                "analysis_id": "33333333-3333-3333-3333-333333333333",
                "assessment_name": "qc-review-pending",
                "status": "QC_VERIFICATION",
            },
        ]
    )

    response = client.get("/api/v1/annotations/qc-unapproved")

    assert response.status_code == 200
    assert response.json() == [
        {"analysis_id": "11111111-1111-1111-1111-111111111111", "assessment_name": "pending-assessment"},
        {"analysis_id": "33333333-3333-3333-3333-333333333333", "assessment_name": "qc-review-pending"},
    ]
