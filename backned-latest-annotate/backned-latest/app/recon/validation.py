"""Validate proposed labels against additional dataset samples."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from app.config import Settings
from app.logging import get_logger
from app.recon.embeddings import embed_image_path, embed_text, load_embedding
from app.recon.ontology import ProposedLabel

logger = get_logger(__name__)


def validate_labels(
    labels: list[ProposedLabel],
    *,
    asset_ids: list[str],
    embedding_paths: dict[str, Path],
    image_paths: dict[str, Path],
    settings: Settings,
    force_fake: bool = False,
    validation_sample: int = 12,
) -> list[ProposedLabel]:
    """Attach validation evidence; demote labels with no support."""
    if not labels or not asset_ids:
        return labels

    sample_ids = asset_ids[:validation_sample]
    out: list[ProposedLabel] = []
    for label in labels:
        support = 0
        method = "embedding_similarity"
        # Start clean — only keep agent evidence that we can re-defend below,
        # or that was already validated. Prefer empty over invented thumbs.
        evidence: list[str] = []
        text_vec = embed_text(
            f"{label.name} {label.definition}",
            settings=settings,
            force_fake=force_fake,
        )

        # Prefer DINO for object-like when available and not faking.
        # Bound open-vocab checks tightly — full-sample DINO per label is too slow on CPU.
        if label.kind == "object" and not force_fake and not settings.skip_model_load:
            try:
                from app.inference.registry import get_runtime

                runtime = get_runtime()
                adapter = runtime.registry.get("dino")
                if adapter is not None and getattr(adapter, "available", True):
                    method = "open_vocab_detection"
                    dino_ids = sample_ids[:4]
                    for aid in dino_ids:
                        if support >= 2 and len(evidence) >= 2:
                            break
                        path = image_paths.get(aid)
                        if path is None or not path.exists():
                            continue
                        try:
                            dets = adapter.predict(  # type: ignore[attr-defined]
                                path,
                                asset_id=aid,
                                labels=[label.name],
                            )
                            if dets:
                                support += 1
                                if aid not in evidence and len(evidence) < 4:
                                    evidence.append(aid)
                        except Exception as exc:  # noqa: BLE001
                            logger.warning(
                                "dino_validation_failed", label=label.name, error=str(exc)
                            )
            except Exception as exc:  # noqa: BLE001
                logger.info("dino_validation_unavailable", error=str(exc))
                method = "embedding_similarity"

        if method == "embedding_similarity" or support == 0:
            if support == 0:
                method = "embedding_similarity"
            for aid in sample_ids:
                path = embedding_paths.get(aid)
                vec = load_embedding(path) if path else None
                if vec is None:
                    img = image_paths.get(aid)
                    if img and img.exists():
                        vec = embed_image_path(img, settings=settings, force_fake=force_fake)
                if vec is None:
                    continue
                dim = min(len(vec), len(text_vec))
                score = float(np.dot(vec[:dim], text_vec[:dim]))
                if score > 0.05 or force_fake or settings.skip_model_load:
                    support += 1
            # Embedding similarity alone is not a defensible visual link for a
            # specific concept — do not attach thumbnails from it.
            if method == "embedding_similarity":
                evidence = []

        if force_fake or settings.skip_model_load:
            support = max(support, 1 if sample_ids else 0)
            # Drop unverified placeholder evidence inherited from agent/fake samples.
            evidence = []

        validated = label.model_copy(
            update={
                "evidence_asset_ids": evidence[:4],
                "evidence_state": (
                    "verified"
                    if evidence and method == "open_vocab_detection"
                    else ("candidate" if evidence else "unverified")
                ),
                "validation": {
                    "supported": support > 0,
                    "support_count": support,
                    "method": method,
                    "sample_size": len(sample_ids),
                    "evidence_basis": (
                        "open_vocab_detection"
                        if evidence
                        else ("embedding_similarity" if support > 0 else "none")
                    ),
                },
            }
        )
        out.append(validated)
    return out
