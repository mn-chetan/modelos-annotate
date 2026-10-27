"""Multimodal expert adapters for Video, Text, and Document pipelines."""

from __future__ import annotations

import hashlib
import json
import numpy as np
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
from typing import Any

from app.inference.contracts import (
    BoundingBoxPercent,
    ModelCapability,
    ModelKey,
    NormalizedDetection,
)
from app.inference.agent_reasoning import call_json_agent
from app.logging import get_logger

logger = get_logger(__name__)


class TrackerAdapter:
    key = "tracker"
    capabilities = [ModelCapability.TRACKING]

    def __init__(self, model_id: str = "bytetrack_expert", device: str = "cpu") -> None:
        self.model_id = model_id
        self.device = device
        self._loaded = False

    def load(self) -> None:
        self._loaded = True

    def track(
        self,
        frames_detections: list[list[dict[str, Any]]],
        iou_threshold: float = 0.3,
    ) -> list[list[dict[str, Any]]]:
        """Associate detections across frames to assign persistent track_ids.

        Each detection has: 'bbox' (dict with x, y, w, h), 'label' (str), 'confidence' (float), etc.
        """
        active_tracks: dict[int, dict[str, Any]] = {}
        lost_tracks: dict[int, int] = {}  # track_id -> frames since last matched
        next_track_id = 1
        tracked_frames = []

        for frame_idx, detections in enumerate(frames_detections):
            unmatched_detections = list(detections)
            matched_tracks = {}

            # First, match active tracks (recent and recently lost)
            all_available_tracks = sorted(
                list(active_tracks.keys()),
                key=lambda tid: lost_tracks.get(tid, 0)
            )

            for track_id in all_available_tracks:
                if not unmatched_detections:
                    break
                track_info = active_tracks[track_id]
                best_iou = 0.0
                best_det_idx = -1
                for det_idx, det in enumerate(unmatched_detections):
                    if det["label"] != track_info["label"]:
                        continue
                    iou = self._calculate_iou(track_info["bbox"], det["bbox"])
                    if iou > best_iou:
                        best_iou = iou
                        best_det_idx = det_idx

                if best_iou > iou_threshold:
                    det = unmatched_detections.pop(best_det_idx)
                    matched_tracks[track_id] = {
                        **det,
                        "track_id": track_id
                    }
                    active_tracks[track_id] = matched_tracks[track_id]
                    lost_tracks[track_id] = 0

            # Increment lost age for unmatched active tracks and prune if they exceeded 30 frames
            for track_id in list(active_tracks.keys()):
                if track_id not in matched_tracks:
                    lost_tracks[track_id] = lost_tracks.get(track_id, 0) + 1
                    if lost_tracks[track_id] > 30:
                        del active_tracks[track_id]
                        del lost_tracks[track_id]

            # Start new tracks for remaining unmatched detections
            for det in unmatched_detections:
                track_id = next_track_id
                next_track_id += 1
                new_track = {
                    **det,
                    "track_id": track_id
                }
                matched_tracks[track_id] = new_track
                active_tracks[track_id] = new_track
                lost_tracks[track_id] = 0

            tracked_frames.append(list(matched_tracks.values()))

        return tracked_frames

    def _calculate_iou(self, box1: Any, box2: Any) -> float:
        if isinstance(box1, dict):
            x1, y1, w1, h1 = box1["x"], box1["y"], box1["w"], box1["h"]
        elif hasattr(box1, "x"):
            x1, y1, w1, h1 = box1.x, box1.y, box1.w, box1.h
        else:
            x1, y1, w1, h1 = box1

        if isinstance(box2, dict):
            x2, y2, w2, h2 = box2["x"], box2["y"], box2["w"], box2["h"]
        elif hasattr(box2, "x"):
            x2, y2, w2, h2 = box2.x, box2.y, box2.w, box2.h
        else:
            x2, y2, w2, h2 = box2

        b1_x1, b1_y1, b1_x2, b1_y2 = x1, y1, x1 + w1, y1 + h1
        b2_x1, b2_y1, b2_x2, b2_y2 = x2, y2, x2 + w2, y2 + h2

        inter_x1 = max(b1_x1, b2_x1)
        inter_y1 = max(b1_y1, b2_y1)
        inter_x2 = min(b1_x2, b2_x2)
        inter_y2 = min(b1_y2, b2_y2)

        inter_area = max(0.0, inter_x2 - inter_x1) * max(0.0, inter_y2 - inter_y1)
        area1 = w1 * h1
        area2 = w2 * h2
        union_area = area1 + area2 - inter_area
        if union_area == 0:
            return 0.0
        return float(inter_area / union_area)


class GlinerAdapter:
    key = "gliner"
    capabilities = [ModelCapability.NER]

    def __init__(self, model_id: str = "gliner2_ner_expert", device: str = "cpu") -> None:
        self.model_id = model_id
        self.device = device
        self._loaded = False

    def load(self) -> None:
        self._loaded = True

    def extract_ner(self, text: str, labels: list[str], settings: Any = None) -> list[dict[str, Any]]:
        """Extract Named Entities using Qwen/Gemini call_json_agent or simple matching fallback."""
        system_prompt = (
            "You are an expert Named Entity Recognition (NER) model. "
            "Identify and extract all entities in the text that match the allowed labels. "
            "Return ONLY a JSON object with this schema:\n"
            "{\n"
            "  \"entities\": [\n"
            "    {\"text\": \"text snippet\", \"label\": \"exact label name\", \"start\": 0, \"end\": 6, \"confidence\": 0.92}\n"
            "  ]\n"
            "}\n"
            "Do not include any explanation or extra JSON wrapper fields. "
            "Character offsets must be 0-indexed and accurate."
        )
        user_payload = {
            "text": text,
            "allowed_labels": labels
        }
        res = call_json_agent(
            system_prompt=system_prompt,
            user_payload=user_payload,
            settings=settings
        )
        if res and isinstance(res.get("entities"), list):
            return res["entities"]

        # Simple deterministic word matching fallback if LLM is unavailable
        entities = []
        words = text.split()
        char_idx = 0
        for w in words:
            clean = w.strip('.,!?;:"()[]{}').lower()
            for label in labels:
                if clean == label.lower():
                    start = text.find(w, char_idx)
                    entities.append({
                        "text": w,
                        "label": label,
                        "start": start,
                        "end": start + len(w),
                        "confidence": 0.80
                    })
            char_idx += len(w) + 1
        return entities


class QwenEmbeddingAdapter:
    key = "qwen3_embedding"
    capabilities = [ModelCapability.EMBEDDING]

    def __init__(self, model_id: str = "qwen3_embedding_expert", device: str = "cpu") -> None:
        self.model_id = model_id
        self.device = device
        self._loaded = False

    def load(self) -> None:
        self._loaded = True

    def embed_text(self, text: str) -> np.ndarray:
        """Generate a deterministic 32-dimensional mock embedding vector from text."""
        h = hashlib.md5(text.encode("utf-8")).digest()
        # Seed generator with hash
        rng = np.random.default_rng(int.from_bytes(h[:4], "little"))
        vec = rng.normal(size=32).astype(np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec


class QwenRerankerAdapter:
    key = "qwen3_reranker"
    capabilities = [ModelCapability.RERANKING]

    def __init__(self, model_id: str = "qwen3_reranker_expert", device: str = "cpu") -> None:
        self.model_id = model_id
        self.device = device
        self._loaded = False

    def load(self) -> None:
        self._loaded = True

    def rerank(self, query: str, candidates: list[str], settings: Any = None) -> list[dict[str, Any]]:
        """Rerank candidates based on relevance to query using call_json_agent."""
        system_prompt = (
            "You are a semantic reranking assistant. "
            "Sort the list of candidate texts by their semantic similarity and relevance to the query. "
            "Return ONLY a JSON object with this schema:\n"
            "{\n"
            "  \"reranked\": [\n"
            "    {\"text\": \"candidate text\", \"score\": 0.95}\n"
            "  ]\n"
            "}\n"
            "Do not include any explanation."
        )
        user_payload = {
            "query": query,
            "candidates": candidates
        }
        res = call_json_agent(
            system_prompt=system_prompt,
            user_payload=user_payload,
            settings=settings
        )
        if res and isinstance(res.get("reranked"), list):
            return res["reranked"]

        # Simple string-match fallback sorting
        ranked = []
        for cand in candidates:
            score = 0.5
            if query.lower() in cand.lower():
                score = 0.9
            ranked.append({"text": cand, "score": score})
        ranked.sort(key=lambda x: x["score"], reverse=True)
        return ranked


class PaddleOcrAdapter:
    key = "paddleocr"
    capabilities = [ModelCapability.OCR]

    def __init__(self, model_id: str = "paddleocr_vl_layout_expert", device: str = "cpu") -> None:
        self.model_id = model_id
        self.device = device
        self._loaded = False

    def load(self) -> None:
        self._loaded = True

    def parse_document(self, text_or_path: str, labels: list[str] | None = None, settings: Any = None) -> list[dict[str, Any]]:
        """Parse structured layout, regions, and tables using Gemini call_json_agent."""
        system_prompt = (
            "You are an OCR and Document Structure analysis expert. "
            "Extract layout regions, text blocks, and tables from the document contents. "
            "Coordinate bounding boxes (x, y, w, h) must be represented as percent of page size (0-100).\n"
            "Return ONLY a JSON object with this schema:\n"
            "{\n"
            "  \"regions\": [\n"
            "    {\n"
            "      \"type\": \"paragraph\" | \"table\" | \"header\" | \"footer\",\n"
            "      \"text\": \"extracted text inside this region\",\n"
            "      \"bbox\": {\"x\": 10.0, \"y\": 15.0, \"w\": 80.0, \"h\": 4.5},\n"
            "      \"confidence\": 0.94\n"
            "    }\n"
            "  ]\n"
            "}\n"
            "Do not include any chain of thought."
        )
        user_payload = {
            "document_snippet": text_or_path[:2000],
            "labels": labels or []
        }
        res = call_json_agent(
            system_prompt=system_prompt,
            user_payload=user_payload,
            settings=settings
        )
        if res and isinstance(res.get("regions"), list):
            return res["regions"]

        # Simple structured document fallback
        lines = text_or_path.splitlines()
        regions = []
        y = 5.0
        for line in lines:
            line = line.strip()
            if not line:
                continue
            regions.append({
                "type": "header" if len(line) < 30 and y == 5.0 else "paragraph",
                "text": line,
                "bbox": {"x": 10.0, "y": y, "w": 80.0, "h": 3.0},
                "confidence": 0.85
            })
            y += 4.5
            if y > 90.0:
                y = 5.0
        return regions
