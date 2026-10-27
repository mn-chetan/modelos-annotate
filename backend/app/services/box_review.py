"""Validated, atomic replacement of image boxes; saving never approves an image."""
from __future__ import annotations

import math
from datetime import UTC, datetime
from uuid import uuid4
from fastapi import HTTPException


def prepare_boxes(annotations, existing, project, asset_id, project_id):
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
        if label not in ontology:
            raise HTTPException(422, f'Unknown project class: {label}')
        if ann.get('geometry_type', 'box') != 'box':
            raise HTTPException(422, 'The demo editor supports boxes only')
        try:
            x, y, w, h = (float(ann.get(k, 0)) for k in ('x', 'y', 'w', 'h'))
        except (ValueError, TypeError):
            raise HTTPException(422, 'Invalid box coordinates')
        if not all(math.isfinite(v) for v in (x, y, w, h)) or w <= 0 or h <= 0:
            raise HTTPException(422, 'Box coordinates must be finite with positive dimensions')
        x, y = max(0., min(100., x)), max(0., min(100., y))
        w, h = min(w, 100-x), min(h, 100-y)
        if w <= 0 or h <= 0:
            raise HTTPException(422, 'Box must intersect the image')
        status = str(ann.get('review_status') or 'pending').lower()
        if status not in {'pending', 'approved', 'rejected', 'edited'}:
            raise HTTPException(422, 'Invalid label review status')
        changed = bool(old and (old.get('label') != label or any(abs(float(old.get(k, 0)) - v) > 1e-7 for k,v in zip(('x','y','w','h'),(x,y,w,h)))))
        row = dict(old or {})
        row.pop('_id', None)
        provenance = dict(row.get('provenance') or {})
        ai_origin = old and (old.get('source') == 'ai' or old.get('model_id') or old.get('confidence') is not None)
        if changed and ai_origin:
            provenance.setdefault('original_ai_label', old.get('label'))
            provenance.setdefault('original_ai_bbox', [old.get(k) for k in ('x','y','w','h')])
            provenance['human_edited'] = True
        if changed:
            provenance['human_edited'] = True
        # Confidence and model evidence are server-owned and survive human edits.
        row.update(id=ann_id, asset_id=asset_id, project_id=project_id, label=label, canonical_label=label, display_label=label,
                   x=x, y=y, w=w, h=h, bbox=[x,y,w,h], geometry_type='box', geometry={'type':'box'},
                   source='human_modified' if changed else row.get('source', 'human'),
                   confidence=row.get('confidence'), provenance=provenance, review_status=status,
                   version=int(row.get('version', 0))+1, created_at=row.get('created_at', now), updated_at=now)
        rows.append(row)
    return rows


async def save_boxes(db, asset, annotations):
    asset_ref = db.assets.col.document(asset['id'])
    snapshot = await asset_ref.get()
    if not snapshot.exists:
        raise HTTPException(404, 'Asset not found')
    project = await db.projects.find_one({'id': asset['project_id']})
    existing = await db.annotations.find({'asset_id': asset['id']}).to_list(length=10000)
    if any((a.get('geometry_type') or 'box') != 'box' for a in existing):
        raise HTTPException(422, 'This asset contains geometry outside the box demo')
    rows = prepare_boxes(annotations, existing, project or {}, asset['id'], asset['project_id'])
    # Firestore batch limit includes deletes and the asset update. Refuse before writing.
    row_ids = {r['id'] for r in rows}
    removed = [a for a in existing if a['id'] not in row_ids]
    if len(rows) + len(removed) + 1 > 500:
        raise HTTPException(422, 'Too many boxes for one atomic save (500 Firestore writes)')
    for row in rows:
        if row['id'] not in {a['id'] for a in existing}:
            foreign = await db.annotations.find_one({'id': row['id']})
            if foreign:
                raise HTTPException(409, 'Annotation ID belongs to another asset')
    # A single atomic commit: a failed save cannot delete previously persisted boxes.
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
