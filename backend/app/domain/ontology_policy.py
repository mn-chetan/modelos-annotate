"""Project ontology as annotation policy: identity, revision, evidence, recommendations."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

EvidenceState = Literal["verified", "candidate", "unverified"]
ChangeActor = Literal["recon", "human", "recommendation"]
RecommendationStatus = Literal["pending", "accepted", "rejected"]

NON_STRUCTURAL_FIELDS = (
    "prevalence_estimate",
    "validation",
    "evidence_asset_ids",
    "evidence_state",
)


def new_concept_id() -> str:
    return str(uuid.uuid4())


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def ensure_concept_ids(ontology: list[dict[str, Any]] | list[Any]) -> list[dict[str, Any]]:
    """Backfill stable concept ids on ontology entries (mutates copies)."""
    out: list[dict[str, Any]] = []
    for item in ontology or []:
        if isinstance(item, str):
            name = item.strip()
            if not name:
                continue
            out.append(
                {
                    "id": new_concept_id(),
                    "name": name,
                    "definition": "",
                    "includes": "",
                    "excludes": "",
                    "aliases": [],
                    "relations": [],
                    "evidence_asset_ids": [],
                    "hard_negative_asset_ids": [],
                    "evidence_state": "unverified",
                    "prevalence_estimate": None,
                    "validation": {},
                    "kind": "object",
                }
            )
            continue
        if not isinstance(item, dict):
            continue
        entry = dict(item)
        if not entry.get("id"):
            entry["id"] = new_concept_id()
        entry.setdefault("hard_negative_asset_ids", [])
        entry.setdefault("evidence_state", derive_evidence_state(entry))
        out.append(entry)
    return out


def derive_evidence_state(entry: dict[str, Any]) -> EvidenceState:
    """Map validation metadata / explicit state onto a product evidence state."""
    explicit = entry.get("evidence_state")
    if explicit in ("verified", "candidate", "unverified"):
        return explicit  # type: ignore[return-value]
    validation = entry.get("validation") if isinstance(entry.get("validation"), dict) else {}
    basis = str(validation.get("evidence_basis") or validation.get("method") or "")
    evid = entry.get("evidence_asset_ids") or []
    if basis == "open_vocab_detection" and evid:
        return "verified"
    if basis == "human_curated" and evid:
        return "verified"
    if evid:
        return "candidate"
    return "unverified"


def normalize_evidence_fields(entry: dict[str, Any]) -> dict[str, Any]:
    """Ensure evidence lists and state are coherent for product display."""
    out = dict(entry)
    out["hard_negative_asset_ids"] = [
        str(x) for x in (out.get("hard_negative_asset_ids") or []) if str(x).strip()
    ]
    positives = [str(x) for x in (out.get("evidence_asset_ids") or []) if str(x).strip()]
    # Positives and hard negatives must not overlap.
    hard = set(out["hard_negative_asset_ids"])
    positives = [x for x in positives if x not in hard]
    out["evidence_asset_ids"] = positives
    out["evidence_state"] = derive_evidence_state(out)
    # Never present empty thumbs as verified.
    if not positives and out["evidence_state"] == "verified":
        out["evidence_state"] = "unverified"
    return out


def ontology_is_human_approved(project_labels_ontology: list[Any] | None, *, plan_approved: bool = False) -> bool:
    """True when the project has an explicit human-controlled ontology structure."""
    if plan_approved:
        return True
    for item in project_labels_ontology or []:
        if isinstance(item, dict) and item.get("approved") is True:
            return True
    return False


def record_change(
    changes: list[dict[str, Any]] | None,
    *,
    actor: ChangeActor,
    kind: str,
    summary: str,
    concept_ids: list[str] | None = None,
    before: Any = None,
    after: Any = None,
    revision: int,
) -> list[dict[str, Any]]:
    entry = {
        "at": _utcnow_iso(),
        "actor": actor,
        "kind": kind,
        "summary": summary,
        "concept_ids": concept_ids or [],
        "revision": revision,
    }
    if before is not None:
        entry["before"] = before
    if after is not None:
        entry["after"] = after
    out = list(changes or [])
    out.append(entry)
    # Keep changelog bounded for document storage.
    if len(out) > 200:
        out = out[-200:]
    return out


def bump_revision(project: Any, *, actor: ChangeActor, kind: str, summary: str, concept_ids: list[str] | None = None) -> int:
    """Increment ontology_revision and append a change entry on a ProjectRow-like object."""
    current = int(getattr(project, "ontology_revision", 0) or 0)
    nxt = current + 1
    project.ontology_revision = nxt
    project.ontology_changes = record_change(
        getattr(project, "ontology_changes", None),
        actor=actor,
        kind=kind,
        summary=summary,
        concept_ids=concept_ids,
        revision=nxt,
    )
    return nxt


def merge_nonstructural_into_approved(
    approved: list[dict[str, Any]],
    proposed: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Refresh prevalence/validation/evidence for matching concepts; never add/remove/rename."""
    by_id = {str(p.get("id")): p for p in proposed if isinstance(p, dict) and p.get("id")}
    by_name = {
        str(p.get("name", "")).casefold(): p
        for p in proposed
        if isinstance(p, dict) and p.get("name")
    }
    out: list[dict[str, Any]] = []
    for entry in approved:
        cur = dict(entry)
        match = None
        cid = str(cur.get("id") or "")
        if cid and cid in by_id:
            match = by_id[cid]
        else:
            match = by_name.get(str(cur.get("name", "")).casefold())
        if match:
            for field in NON_STRUCTURAL_FIELDS:
                if field in match and match[field] is not None:
                    # Do not downgrade human-curated verified positives with recon candidates
                    # unless recon provides verified detector evidence.
                    if field == "evidence_asset_ids":
                        if cur.get("evidence_state") == "verified" and derive_evidence_state(match) != "verified":
                            continue
                        if cur.get("evidence_state") == "verified" and list(cur.get("evidence_asset_ids") or []):
                            # Keep human/curated verified set; allow union with new verified.
                            if derive_evidence_state(match) == "verified":
                                merged = list(dict.fromkeys([*(cur.get("evidence_asset_ids") or []), *(match.get("evidence_asset_ids") or [])]))
                                cur["evidence_asset_ids"] = merged[:6]
                            continue
                    cur[field] = match[field]
            cur = normalize_evidence_fields(cur)
        out.append(cur)
    return out


def recommendation_fingerprint(
    *,
    rec_type: str,
    concept_ids: list[str],
    proposal: dict[str, Any],
) -> str:
    raw = f"{rec_type}|{','.join(sorted(concept_ids))}|{sorted(proposal.items())}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def build_deterministic_recommendations(
    ontology: list[dict[str, Any]],
    *,
    rejected_fingerprints: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Heuristic, evidence-backed recommendations (no LLM required; deterministic tests)."""
    rejected = rejected_fingerprints or set()
    recs: list[dict[str, Any]] = []
    for entry in ontology:
        if not isinstance(entry, dict) or not entry.get("name"):
            continue
        cid = str(entry.get("id") or "")
        name = str(entry["name"])
        definition = (entry.get("definition") or "").strip()
        excludes = (entry.get("excludes") or "").strip()
        evid = list(entry.get("evidence_asset_ids") or [])
        state = derive_evidence_state(entry)

        if not definition:
            proposal = {
                "type": "tighten_definition",
                "name": name,
                "definition": f"Objects that annotators should mark as {name} in this dataset.",
            }
            fp = recommendation_fingerprint(rec_type="tighten_definition", concept_ids=[cid], proposal=proposal)
            if fp not in rejected:
                recs.append(
                    {
                        "id": new_concept_id(),
                        "type": "tighten_definition",
                        "concept_ids": [cid],
                        "proposal": proposal,
                        "rationale": f"{name} has no definition yet; a short policy definition improves consistent labeling.",
                        "evidence_asset_ids": evid[:4],
                        "impact": "Updates definition only; does not rename or merge concepts.",
                        "status": "pending",
                        "fingerprint": fp,
                        "created_at": _utcnow_iso(),
                        "decided_at": None,
                    }
                )

        if state in ("candidate", "unverified") and evid:
            proposal = {
                "type": "confirm_evidence",
                "name": name,
                "evidence_state": "verified",
            }
            fp = recommendation_fingerprint(rec_type="confirm_evidence", concept_ids=[cid], proposal=proposal)
            if fp not in rejected:
                recs.append(
                    {
                        "id": new_concept_id(),
                        "type": "confirm_evidence",
                        "concept_ids": [cid],
                        "proposal": proposal,
                        "rationale": f"Examples on {name} are not yet verified as concept-specific positives.",
                        "evidence_asset_ids": evid[:4],
                        "impact": "Marks existing examples as verified positives; does not change structure.",
                        "status": "pending",
                        "fingerprint": fp,
                        "created_at": _utcnow_iso(),
                        "decided_at": None,
                    }
                )

        if not excludes and evid:
            proposal = {
                "type": "add_exclusion_rule",
                "name": name,
                "excludes": f"Visually similar objects that should not receive the {name} label.",
            }
            fp = recommendation_fingerprint(rec_type="add_exclusion_rule", concept_ids=[cid], proposal=proposal)
            if fp not in rejected:
                recs.append(
                    {
                        "id": new_concept_id(),
                        "type": "add_exclusion_rule",
                        "concept_ids": [cid],
                        "proposal": proposal,
                        "rationale": f"{name} has no exclusion boundary; adding one reduces over-labeling.",
                        "evidence_asset_ids": evid[:4],
                        "impact": "Adds an exclusion rule string; does not delete concepts.",
                        "status": "pending",
                        "fingerprint": fp,
                        "created_at": _utcnow_iso(),
                        "decided_at": None,
                    }
                )

    # Cap pending recommendations for UI clarity.
    return recs[:12]


def apply_recommendation_to_ontology(
    ontology: list[dict[str, Any]],
    rec: dict[str, Any],
) -> list[dict[str, Any]]:
    """Apply an accepted recommendation structurally/non-structurally as appropriate."""
    out = [dict(x) for x in ontology]
    by_id = {str(x.get("id")): i for i, x in enumerate(out) if x.get("id")}
    concept_ids = [str(x) for x in (rec.get("concept_ids") or [])]
    proposal = rec.get("proposal") if isinstance(rec.get("proposal"), dict) else {}
    rec_type = str(rec.get("type") or proposal.get("type") or "")

    if rec_type == "new_concept" and proposal.get("name"):
        name = str(proposal["name"]).strip()
        if name and name.casefold() not in {str(x.get("name", "")).casefold() for x in out}:
            out.append(
                normalize_evidence_fields(
                    {
                        "id": new_concept_id(),
                        "name": name,
                        "definition": str(proposal.get("definition") or ""),
                        "includes": str(proposal.get("includes") or ""),
                        "excludes": str(proposal.get("excludes") or ""),
                        "aliases": list(proposal.get("aliases") or []),
                        "relations": [],
                        "evidence_asset_ids": list(rec.get("evidence_asset_ids") or [])[:4],
                        "hard_negative_asset_ids": [],
                        "evidence_state": "candidate",
                        "kind": "object",
                        "source": "recommendation",
                        "approved": True,
                    }
                )
            )
        return out

    for cid in concept_ids:
        idx = by_id.get(cid)
        if idx is None:
            continue
        entry = dict(out[idx])
        if rec_type == "tighten_definition" and proposal.get("definition"):
            entry["definition"] = str(proposal["definition"])
        elif rec_type == "add_exclusion_rule" and proposal.get("excludes"):
            entry["excludes"] = str(proposal["excludes"])
        elif rec_type == "add_inclusion_rule" and proposal.get("includes"):
            entry["includes"] = str(proposal["includes"])
        elif rec_type == "add_alias" and proposal.get("alias"):
            aliases = list(entry.get("aliases") or [])
            alias = str(proposal["alias"]).strip()
            if alias and alias.casefold() not in {a.casefold() for a in aliases}:
                aliases.append(alias)
            entry["aliases"] = aliases
        elif rec_type == "rename" and proposal.get("name"):
            entry["name"] = str(proposal["name"]).strip()
        elif rec_type == "confirm_evidence":
            entry["evidence_state"] = "verified"
            validation = dict(entry.get("validation") or {})
            validation["evidence_basis"] = "human_curated"
            entry["validation"] = validation
        out[idx] = normalize_evidence_fields(entry)
    return out


def rejected_fingerprints(recommendations: list[dict[str, Any]] | None) -> set[str]:
    out: set[str] = set()
    for rec in recommendations or []:
        if isinstance(rec, dict) and rec.get("status") == "rejected" and rec.get("fingerprint"):
            out.add(str(rec["fingerprint"]))
    return out


def merge_recommendations(
    existing: list[dict[str, Any]] | None,
    fresh: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep accepted/rejected history; add new pending that are not rejected duplicates."""
    kept: list[dict[str, Any]] = []
    rejected = rejected_fingerprints(existing)
    pending_fps: set[str] = set()
    for rec in existing or []:
        if not isinstance(rec, dict):
            continue
        status = rec.get("status")
        if status in ("accepted", "rejected"):
            kept.append(rec)
        elif status == "pending" and rec.get("fingerprint"):
            pending_fps.add(str(rec["fingerprint"]))
            kept.append(rec)
    for rec in fresh:
        fp = str(rec.get("fingerprint") or "")
        if not fp or fp in rejected or fp in pending_fps:
            continue
        kept.append(rec)
        pending_fps.add(fp)
    return kept
