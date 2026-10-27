"""Florence-2 vision-language adapter for captions and label assistance."""

from __future__ import annotations

import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.errors import ModelUnavailableError
from app.inference.contracts import LabelSuggestion, ModelCapability, ModelKey
from app.inference.device import resolve_device
from app.logging import get_logger

logger = get_logger(__name__)


class FlorenceAdapter:
    key = ModelKey.FLORENCE.value
    capabilities = [ModelCapability.CAPTION, ModelCapability.LABEL_ASSIST]

    def __init__(
        self,
        *,
        model_id: str = "microsoft/Florence-2-base",
        revision: str | None = "5ca5edf5bd017b9919c05d08aebef5e4c7ac3bac",
        device_preference: str = "auto",
        cache_dir: Path | None = None,
    ) -> None:
        self.model_id = model_id
        self.revision = revision
        self.device = resolve_device(device_preference)
        self.cache_dir = cache_dir
        self._model: Any | None = None
        self._processor: Any | None = None
        self.load_duration_ms: int | None = None
        self._loaded: bool = False

    def load(self) -> None:
        if getattr(self, "_loaded", False):
            return
        start = time.perf_counter()
        logger.info(
            "model_load_start",
            model_key=self.key,
            model_id=self.model_id,
            device=self.device,
        )
        try:
            import torch
            import transformers
            from transformers import AutoModelForCausalLM, AutoProcessor
        except ImportError as exc:
            raise ModelUnavailableError(
                "transformers is required for Florence-2",
                details={"hint": "uv pip install transformers"},
            ) from exc

        try:
            kwargs: dict[str, Any] = {"trust_remote_code": True}
            if self.revision:
                kwargs["revision"] = self.revision
            if self.cache_dir is not None:
                kwargs["cache_dir"] = str(self.cache_dir)
            self._processor = AutoProcessor.from_pretrained(self.model_id, **kwargs)
            dtype = torch.float32 if self.device == "cpu" else torch.float16
            self._model = AutoModelForCausalLM.from_pretrained(
                self.model_id,
                torch_dtype=dtype,
                attn_implementation="eager",
                **kwargs,
            )
            self._model.to(self.device)
            self._model.eval()
            self._validate_loaded_model(torch)
        except Exception as exc:  # noqa: BLE001
            raise ModelUnavailableError(
                f"Failed to load Florence-2 {self.model_id}: {exc}",
                details={
                    "model_id": self.model_id,
                    "device": self.device,
                    "next_step": "Ensure HF access for microsoft/Florence-2-base",
                },
            ) from exc

        self.load_duration_ms = int((time.perf_counter() - start) * 1000)
        self._loaded = True
        logger.info(
            "model_load_complete",
            model_key=self.key,
            model_id=self.model_id,
            device=self.device,
            duration_ms=self.load_duration_ms,
        )

    def _validate_loaded_model(self, torch: Any) -> None:
        """Reject a partially initialized Florence model before registry exposure."""
        model = self._model
        processor = self._processor
        if model is None or processor is None:
            raise ModelUnavailableError("Florence model or processor was not initialized")

        language_model = getattr(model, "language_model", None)
        if language_model is None:
            language_model = getattr(getattr(model, "model", None), "language_model", None)
        shared = getattr(language_model, "model", language_model)
        shared_weight = getattr(getattr(shared, "shared", None), "weight", None)
        if shared_weight is None:
            raise ModelUnavailableError("Florence language-model shared embeddings are missing")

        required_aliases = [
            getattr(language_model, "lm_head", None) or getattr(model, "lm_head", None),
            getattr(getattr(shared, "encoder", None), "embed_tokens", None),
            getattr(getattr(shared, "decoder", None), "embed_tokens", None),
        ]
        if any(module is None or getattr(module, "weight", None) is None for module in required_aliases):
            raise ModelUnavailableError("Florence required language-model embedding aliases are missing")
        if any(module.weight.shape != shared_weight.shape for module in required_aliases):
            raise ModelUnavailableError("Florence language-model embedding shapes are incompatible")
        if any(module.weight.data_ptr() != shared_weight.data_ptr() for module in required_aliases):
            raise ModelUnavailableError("Florence language-model embeddings are not tied to shared weights")

        # A one-token generation validates processor/model compatibility and
        # catches a load that only constructed the module graph successfully.
        from PIL import Image
        image = Image.new("RGB", (64, 64), color=(0, 0, 0))
        inputs = processor(text="<CAPTION>", images=image, return_tensors="pt")
        inputs = {key: value.to(self.device) for key, value in inputs.items()}
        with torch.inference_mode():
            generated = model.generate(
                input_ids=inputs["input_ids"],
                pixel_values=inputs["pixel_values"],
                max_new_tokens=1,
                num_beams=1,
                do_sample=False,
                use_cache=False,
            )
        if generated is None or getattr(generated, "numel", lambda: 0)() == 0:
            raise ModelUnavailableError("Florence minimal inference returned no tokens")

    def assist(
        self,
        image_path: Path | None,
        *,
        asset_id: str | None = None,
        goal: str = "",
        labels: list[str] | None = None,
        strategy: str = "generic",
    ) -> LabelSuggestion:
        if image_path is None:
            # Metadata-only assist: refine taxonomy from goal without inventing detections
            base = labels[:] if labels else []
            if not base and goal:
                words = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", goal.lower())
                stop = {"the", "and", "for", "with", "that", "this", "from", "into", "detect"}
                base = [w for w in words if w not in stop][:8] or ["object"]
            return LabelSuggestion(
                labels=base,
                caption=None,
                rationale="Taxonomy refined from project metadata (no image sent).",
                model_id=self.model_id,
                model_key=self.key,
                inferred_at=datetime.now(UTC),
                provenance={"engine": "florence-metadata", "strategy": strategy, "goal": goal},
            )

        if getattr(self, "_loaded", False):
            logger.info(
                "model_reuse",
                model_key=self.key,
                registry_id=getattr(self, "registry_id", "unknown"),
            )
        else:
            self.load()
        if self._model is None or self._processor is None:
            raise ModelUnavailableError(
                f"Florence model {self.model_id} is not loaded or is unavailable.",
                details={
                    "model_id": self.model_id,
                    "device": self.device,
                },
            )

        from PIL import Image

        image = Image.open(image_path).convert("RGB")
        task = "<CAPTION>"
        inputs = self._processor(text=task, images=image, return_tensors="pt")
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        generated = self._model.generate(
            input_ids=inputs["input_ids"],
            pixel_values=inputs["pixel_values"],
            max_new_tokens=64,
            num_beams=3,
            do_sample=False,
            use_cache=False,
        )
        caption = self._processor.batch_decode(generated, skip_special_tokens=True)[0]
        caption = caption.replace(task, "").strip()

        suggested = labels[:] if labels else []
        # Pull noun-ish tokens from caption as suggestions (honest assist, not detections)
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", caption.lower()):
            if token not in suggested and token not in {"the", "and", "with", "from"}:
                suggested.append(token)
            if len(suggested) >= 12:
                break

        return LabelSuggestion(
            labels=suggested,
            caption=caption,
            rationale=f"Florence caption assist (strategy={strategy})",
            model_id=self.model_id,
            model_key=self.key,
            inferred_at=datetime.now(UTC),
            provenance={
                "engine": "transformers-florence2",
                "task": task,
                "asset_id": asset_id,
                "goal": goal,
            },
        )
