"""Validated, atomic replacement of a text document's labels; saving never approves it.

Mirrors box_review for text: entity spans keep their character offsets and text, document
labels (sentiment, category) keep their kind, every label carries its own review decision, and
a correction to an AI label records what the AI originally said.
"""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4
from fastapi import HTTPException

TEXT_GEOMETRIES = {'text_span', 'text_classification', 'text_relation'}
DECISIONS = {'pending', 'approved', 'rejected', 'edited'}


def _span(ann) -> tuple[int, int, str]:
    geometry = ann.get('geometry') or ann.get('text_span') or {}
    try:
        start, end = int(geometry.get('start')), int(geometry.get('end'))
    except (TypeError, ValueError):
        raise HTTPException(422, 'An entity needs whole-number start and end offsets')
    return start, end, str(geometry.get('text') or '')


def text_result_sound(quality, annotations, classes) -> bool:
    """Whether the AI's text result may be approved by the line alone.

    The line, not the model's own fixed bar, decides confidence. What still sends a document to
    a person: structural errors, semantic conflicts, no labels, or a label outside the classes.
    """
    if not annotations or quality.get('errors') or quality.get('semantic_conflicts'):
        return False
    if any(quality.get(flag) for flag in ('invalid_spans', 'invalid_labels', 'invalid_output', 'no_semantic_result')):
        return False
    names = set(classes or [])
    return not names or all(a.get('label') in names for a in annotations if a.get('geometry_type') != 'text_relation')


def prepare_spans(annotations, existing, project, asset_id, project_id, text_length=None):
    ontology = set(project.get('labels') or [])
    ontology.update(c.get('name') for c in project.get('label_ontology', []) if isinstance(c, dict))
    by_id = {a['id']: a for a in existing}
    rows, ids = [], set()
    now = datetime.now(UTC)
    for ann in annotations:
        ann_id = str(ann.get('id') or uuid4())
        if ann_id in ids:
            raise HTTPException(422, 'Duplicate annotation ID')
        ids.add(ann_id)
        old = by_id.get(ann_id)
        label = str(ann.get('label') or '').strip()
        # A label the AI produced may sit outside the project's classes; keeping it is allowed.
        if label not in ontology and not (old and old.get('label') == label):
            raise HTTPException(422, f'Unknown project class: {label}')
        kind = ann.get('geometry_type') or (old or {}).get('geometry_type') or 'text_span'
        if kind not in TEXT_GEOMETRIES:
            raise HTTPException(422, 'Text documents take entity spans and document labels only')
        status = str(ann.get('review_status') or 'pending').lower()
        if status not in DECISIONS:
            raise HTTPException(422, 'Invalid label review status')

        row = dict(old or {})
        row.pop('_id', None)
        provenance = dict(row.get('provenance') or {})
        geometry = dict(row.get('geometry') or {})
        changed = bool(old and old.get('label') != label)
        if kind == 'text_span':
            start, end, text = _span(ann)
            if start < 0 or end <= start or (text_length is not None and end > text_length):
                raise HTTPException(422, 'Entity offsets must fall inside the document')
            old_span = _span(old) if old and (old.get('geometry_type') or 'text_span') == 'text_span' else None
            if old_span and old_span[:2] != (start, end):
                changed = True
                provenance.setdefault('original_ai_span', [old_span[0], old_span[1]])
            geometry.update(start=start, end=end, text=text)
            row['text_span'] = {'start': start, 'end': end, 'text': text}
        elif kind == 'text_relation' and ann.get('geometry'):
            geometry.update(ann['geometry'])
        ai_origin = old and (old.get('source') == 'ai' or old.get('model_id') or old.get('confidence') is not None)
        if changed and ai_origin:
            provenance.setdefault('original_ai_label', old.get('label'))
        if changed:
            provenance['human_edited'] = True
        # Confidence and model evidence are server-owned and survive human edits.
        row.update(id=ann_id, asset_id=asset_id, project_id=project_id, label=label, canonical_label=label, display_label=label,
                   geometry_type=kind, geometry=geometry, x=0.0, y=0.0, w=0.0, h=0.0,
                   source='human_modified' if changed and ai_origin else row.get('source', 'human'),
                   confidence=row.get('confidence'), provenance=provenance, review_status=status,
                   version=int(row.get('version', 0)) + 1, created_at=row.get('created_at', now), updated_at=now)
        rows.append(row)
    return rows


async def save_spans(db, asset, annotations):
    asset_ref = db.assets.col.document(asset['id'])
    snapshot = await asset_ref.get()
    if not snapshot.exists:
        raise HTTPException(404, 'Asset not found')
    project = await db.projects.find_one({'id': asset['project_id']})
    existing = await db.annotations.find({'asset_id': asset['id']}).to_list(length=10000)
    text = ((asset.get('text_analysis') or {}).get('text')) or None
    rows = prepare_spans(annotations, existing, project or {}, asset['id'], asset['project_id'], len(text) if text else None)
    row_ids = {r['id'] for r in rows}
    removed = [a for a in existing if a['id'] not in row_ids]
    # Firestore batch limit includes deletes and the asset update. Refuse before writing.
    if len(rows) + len(removed) + 1 > 500:
        raise HTTPException(422, 'Too many labels for one atomic save (500 Firestore writes)')
    existing_ids = {a['id'] for a in existing}
    for row in rows:
        if row['id'] not in existing_ids and await db.annotations.find_one({'id': row['id']}):
            raise HTTPException(409, 'Annotation ID belongs to another asset')
    # A single atomic commit: a failed save cannot delete previously persisted labels.
    from google.cloud.firestore_v1 import LastUpdateOption
    batch = db.client.batch()
    for old in removed:
        batch.delete(db.annotations.col.document(old['id']))
    for row in rows:
        batch.set(db.annotations.col.document(row['id']), row)
    batch.update(asset_ref, {'updated_at': datetime.now(UTC), 'review_status': 'needs_review',
                            'annotation_count': len(rows), 'is_locked': False,
                            'workflow_status': 'HUMAN_REVIEW', 'current_real_status': 'HUMAN_REVIEW', 'qc_status': None},
                 option=LastUpdateOption(snapshot.update_time))
    await batch.commit()
    return {'status': 'success', 'count': len(rows), 'asset_id': asset['id']}
