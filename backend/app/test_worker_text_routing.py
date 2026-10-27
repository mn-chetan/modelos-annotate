"""Regression tests for batch worker asset modality resolution and text batch execution routing."""
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.jobs.worker import resolve_asset_modality, BatchWorker
from app.agent.graphs.agentic_pipeline_graph import create_execution_plan_node


def test_resolve_asset_modality_helper():
    print("--- Test 1: resolve_asset_modality helper ---")
    # Asset with filename text-input.txt
    mock_asset_txt = MagicMock()
    mock_asset_txt.filename = "text-input.txt"
    mock_asset_txt.modality = None
    mock_asset_txt.content_type = "text/plain"

    mod = resolve_asset_modality(mock_asset_txt, None, Path("storage/test/text-input.txt"))
    assert mod == "text", f"Expected 'text', got '{mod}'"

    # Asset with .jpg
    mock_asset_jpg = MagicMock()
    mock_asset_jpg.filename = "photo.jpg"
    mock_asset_jpg.modality = None
    mock_asset_jpg.content_type = "image/jpeg"

    mod_jpg = resolve_asset_modality(mock_asset_jpg, None, Path("storage/test/photo.jpg"))
    assert mod_jpg == "image", f"Expected 'image', got '{mod_jpg}'"

    # Asset with .mp4
    mock_asset_mp4 = MagicMock()
    mock_asset_mp4.filename = "video.mp4"
    mock_asset_mp4.modality = None
    mock_asset_mp4.content_type = "video/mp4"

    mod_mp4 = resolve_asset_modality(mock_asset_mp4, None, Path("storage/test/video.mp4"))
    assert mod_mp4 == "video", f"Expected 'video', got '{mod_mp4}'"

    print("[PASS] resolve_asset_modality correctly identifies text, image, and video modalities.")


@pytest.mark.asyncio
async def test_text_worker_routing_no_pil(tmp_path: Path):
    print("--- Test 2: Text worker routing without PIL.Image.open ---")
    # Create temporary text file
    txt_file = tmp_path / "text-input.txt"
    txt_file.write_text("Customer service was excellent and delivery was fast.", encoding="utf-8")

    # Mocks for worker dependencies
    mock_asset = MagicMock()
    mock_asset.id = "e067843f-1d12-46d0-aff9-2edd08996f4b"
    mock_asset.filename = "text-input.txt"
    mock_asset.storage_path = str(txt_file)
    mock_asset.content_type = "text/plain"

    mock_project = MagicMock()
    mock_project.id = "proj-123"
    mock_project.labels = ["POSITIVE", "NEGATIVE"]
    mock_project.label_ontology = ["POSITIVE", "NEGATIVE"]
    mock_project.task_type = "Sentiment Annotation"
    mock_project.modality = "text"
    mock_project.quality_policy = {}
    mock_project.goal = "Analyze customer sentiment"

    mock_batch = MagicMock()
    mock_batch.id = "dc3ed6c8-27d9-4d82-abeb-8c9ed0929423"
    mock_batch.project_id = "proj-123"
    mock_batch.status = "running"
    mock_batch.workflow = []

    mock_item = MagicMock()
    mock_item.id = "item-789"
    mock_item.asset_id = mock_asset.id
    mock_item.attempt = 1

    mock_storage = MagicMock()
    mock_storage.resolve = MagicMock(return_value=txt_file)

    mock_runtime = MagicMock()
    mock_runtime.registry.status.return_value = []

    mock_db = MagicMock()

    # Track calls to inspect_scene / PIL Image.open
    pil_opened = False

    def fake_pil_open(*args, **kwargs):
        nonlocal pil_opened
        pil_opened = True
        raise RuntimeError("PIL.Image.open SHOULD NOT BE CALLED FOR TEXT ASSET")

    with patch("PIL.Image.open", side_effect=fake_pil_open):
        modality = resolve_asset_modality(mock_asset, mock_project, txt_file)
        assert modality == "text", f"Expected text modality, got {modality}"
        assert not pil_opened, "PIL.Image.open was incorrectly invoked for text asset"

    print("[PASS] Text asset routing verified: PIL.Image.open was NOT called.")


@pytest.mark.asyncio
async def test_sentiment_text_planner_execution():
    print("--- Test 3: Sentiment Text Planner Execution ---")
    mock_intent = MagicMock()
    mock_intent.task_type = "Sentiment Annotation"
    mock_intent.requested_labels = ["POSITIVE", "NEGATIVE"]

    state = {
        "parsed_intent": mock_intent,
        "available_models": {},
        "capability_gaps": [],
        "project_snapshot": {
            "modality": "text",
            "task_type": "Sentiment Annotation",
            "labels": ["POSITIVE", "NEGATIVE"],
        },
        "asset_snapshot": {"id": "e067843f-1d12-46d0-aff9-2edd08996f4b"},
        "timings": {},
    }

    res = await create_execution_plan_node(state)
    plan = res["execution_plan"]
    assert plan["models"] == ["text_sentiment_analysis"]
    assert plan["task_type"] == "SENTIMENT_ANALYSIS"
    print("[PASS] Sentiment text planner selected text_sentiment_analysis.")


def run_all():
    test_resolve_asset_modality_helper()
    asyncio.run(test_text_worker_routing_no_pil(Path(tempfile.gettempdir())))
    asyncio.run(test_sentiment_text_planner_execution())
    print("\nALL WORKER TEXT ROUTING TESTS PASSED!")


if __name__ == "__main__":
    run_all()
