"""Focused regressions: real-pipeline failure semantics, review evidence and approved export."""
import io
import json
import zipfile
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.services.box_review import prepare_boxes, save_boxes
from app.services.demo_inference import ai_review_status, approval_line, run_demo_image
from app.services.export import ExportService
from app.config import Settings
from app.db.models import MongoDoc
from app.inference.registry import create_registry_from_settings
from app.storage.files import FileStorage


class Cursor:
    def __init__(self, rows): self.rows = rows
    async def to_list(self, length=None): return self.rows[:length]


class Collection:
    def __init__(self, rows): self.rows = rows
    def find(self, query):
        def match(r):
            for k,v in query.items():
                if isinstance(v, dict) and '$in' in v:
                    assert isinstance(v['$in'], list), 'Firestore $in needs a list'
                    if r.get(k) not in v['$in']: return False
                elif r.get(k) != v: return False
            return True
        return Cursor([dict(r) for r in self.rows if match(r)])
    async def find_one(self, query):
        rows = await self.find(query).to_list(1)
        return rows[0] if rows else None


def test_box_edits_keep_server_owned_evidence_and_clamp():
    now=datetime.now(UTC)
    old={'id':'a','label':'car','x':1,'y':2,'w':3,'h':4,'source':'ai','confidence':.613,
         'model_id':'dino-real','provenance':{'raw_model_confidence':.613},'created_at':now,'version':3}
    row=prepare_boxes([dict(old,label='bus',x=95,y=96,w=20,h=20,confidence=1,model_id='fake',provenance={},review_status='rejected')],[old],{'labels':['car','bus']},'image','project')[0]
    assert (row['x'],row['y'],row['w'],row['h'])==(95,96,5,4)
    assert row['confidence']==.613 and row['model_id']=='dino-real'
    assert row['provenance']['raw_model_confidence']==.613
    assert row['provenance']['original_ai_label']=='car' and row['provenance']['human_edited']
    assert row['review_status']=='rejected' and row['version']==4


@pytest.mark.parametrize('patch',[{'label':'unknown'},{'x':float('inf')},{'w':0},{'h':-1},{'geometry_type':'polygon'}])
def test_bad_box_rejected_before_any_write(patch):
    with pytest.raises(HTTPException):
        prepare_boxes([dict({'label':'car','x':0,'y':0,'w':1,'h':1},**patch)],[],{'labels':['car']},'asset','project')


@pytest.mark.asyncio
async def test_failed_inference_never_publishes_partial_predictions(tmp_path,monkeypatch):
    image=tmp_path/'image.jpg';image.write_bytes(b'image')
    updates=[]
    class Assets:
        async def update_one(self,q,u): updates.append(u['$set'])
    db=SimpleNamespace(assets=Assets(),model_runs=SimpleNamespace(insert_one=AsyncMock(),update_one=AsyncMock()))
    registry=SimpleNamespace(try_load=lambda key:key!='dino',get=lambda key:SimpleNamespace(model_id=key,assist=lambda *a,**kw:SimpleNamespace(caption='real caption')), _errors={'dino':'offline'})
    runtime=SimpleNamespace(registry=registry,detect=lambda *a,**kw:[])
    publish=AsyncMock();monkeypatch.setattr('app.services.demo_inference.AnnotationService',lambda db:SimpleNamespace(replace_ai_detections=publish))
    with pytest.raises(RuntimeError,match='dino.*offline'):
        await run_demo_image(db,Settings(),SimpleNamespace(resolve=lambda s:image),runtime,MongoDoc(id='p',modality='image',task_type='object_detection',labels=['car']),MongoDoc(id='a',storage_path='image'),MongoDoc(id='i'),'b')
    publish.assert_not_called()
    assert not any(u.get('ai_completed_at') for u in updates)
    assert 'dino' in updates[-1]['inference_error']


def test_demo_refuses_mock_registry():
    with pytest.raises(ValueError,match='real model'):
        create_registry_from_settings(Settings(demo_image_pipeline=True,force_fake=True))


@pytest.mark.asyncio
async def test_export_requires_image_approval_and_excludes_rejected(tmp_path):
    now=datetime.now(UTC)
    project={'id':'p','name':'Demo','labels':['car','bus'],'modality':'image'}
    asset={'id':'im','project_id':'p','filename':'test.jpg','width':1000,'height':500,'review_status':'needs_review','created_at':now}
    annotations=[{'id':str(i),'project_id':'p','asset_id':'im','label':'car','x':10,'y':20,'w':30,'h':40,'confidence':.8,'source':'ai','review_status':status,'created_at':now} for i,status in enumerate(['approved','rejected'])]
    db=SimpleNamespace(projects=Collection([project]),assets=Collection([asset]),annotations=Collection(annotations),masks=Collection([]))
    service=ExportService(db,FileStorage(tmp_path))
    _,_,_,summary=await service.export_project('p',fmt='coco',include_images=False)
    assert summary['image_count']==0 and summary['annotation_count']==0
    asset['review_status']='final_approved'
    data,_,_,summary=await service.export_project('p',fmt='coco',include_images=False)
    assert summary['annotation_count']==1 and summary['image_count']==1
    coco=json.loads(zipfile.ZipFile(io.BytesIO(data)).read('annotations/instances.json'))
    assert coco['annotations'][0]['bbox']==[100,100,300,200]
    data,_,_,summary=await service.export_project('p',fmt='yolo',include_images=False)
    z=zipfile.ZipFile(io.BytesIO(data));label_file=next(n for n in z.namelist() if n.startswith('labels/') and n.endswith('.txt'))
    line=z.read(label_file).decode().split()
    assert list(map(float,line[1:]))==[.25,.4,.3,.4]


@pytest.mark.asyncio
async def test_empty_success_is_explicit_and_goes_to_review(tmp_path,monkeypatch):
    image=tmp_path/'blank.png';image.write_bytes(b'file')
    updates=[]
    class Assets:
        async def update_one(self,q,u): updates.append(u['$set'])
    db=SimpleNamespace(assets=Assets(),model_runs=SimpleNamespace(insert_one=AsyncMock(),update_one=AsyncMock()))
    adapter=SimpleNamespace(model_id='real',assist=lambda *a,**kw:SimpleNamespace(caption='Blank image'))
    runtime=SimpleNamespace(registry=SimpleNamespace(try_load=lambda k:True,get=lambda k:adapter),detect=lambda *a,**kw:[])
    publish=AsyncMock();complete=AsyncMock()
    monkeypatch.setattr('app.services.demo_inference.AnnotationService',lambda db:SimpleNamespace(replace_ai_detections=publish))
    monkeypatch.setattr('app.services.demo_inference.BatchService',lambda *a:SimpleNamespace(complete_item=complete))
    await run_demo_image(db,Settings(),SimpleNamespace(resolve=lambda s:image),runtime,MongoDoc(id='p',modality='image',task_type='object_detection',labels=['car']),MongoDoc(id='a',storage_path='file'),MongoDoc(id='i'),'b')
    assert publish.await_args.args[1]==[]
    assert updates[-1]['review_status']=='needs_review' and updates[-1]['ai_completed_at']
    assert complete.await_args.kwargs['status']=='succeeded'


@pytest.mark.asyncio
async def test_save_commit_failure_keeps_previous_rows(tmp_path):
    """A failed commit must never execute the old delete-all/insert sequence."""
    old={'id':'a','asset_id':'im','project_id':'p','label':'car','x':10,'y':20,'w':30,'h':40}
    annotations=Collection([old]);annotations.delete_many=AsyncMock(side_effect=AssertionError('non-atomic delete'))
    annotations.insert_many=AsyncMock(side_effect=AssertionError('non-atomic insert'))
    annotations.col=SimpleNamespace(document=lambda id:('annotations',id))
    snapshot=SimpleNamespace(exists=True,update_time=datetime.now(UTC))
    asset_ref=SimpleNamespace(get=AsyncMock(return_value=snapshot))
    batch=SimpleNamespace(delete=lambda *a:None,set=lambda *a:None,update=lambda *a,**kw:None,commit=AsyncMock(side_effect=RuntimeError('network failure')))
    db=SimpleNamespace(assets=SimpleNamespace(col=SimpleNamespace(document=lambda id:asset_ref)),
                       projects=Collection([{'id':'p','labels':['car']}]),annotations=annotations,
                       client=SimpleNamespace(batch=lambda:batch))
    with pytest.raises(RuntimeError,match='network failure'):
        await save_boxes(db,{'id':'im','project_id':'p'},[dict(old,x=40)])
    assert annotations.rows==[old]
    annotations.delete_many.assert_not_called()
    annotations.insert_many.assert_not_called()


def test_ai_approves_only_when_every_box_clears_the_line():
    project = {"quality_policy": {"auto_approve_threshold": 0.9}, "confidence_threshold": 0.5}
    assert approval_line(project) == 0.9
    assert ai_review_status(project, [0.95, 0.91]) == "auto_approved"
    assert ai_review_status(project, [0.95, 0.89]) == "needs_review"
    assert ai_review_status(project, []) == "needs_review"
    assert ai_review_status(project, [0.95, None]) == "needs_review"
    assert approval_line({"confidence_threshold": 0.7}) == 0.7
    assert approval_line({}) == 0.95
