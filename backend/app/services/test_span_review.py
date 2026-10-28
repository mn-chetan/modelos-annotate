import pytest
from fastapi import HTTPException

from app.services.span_review import prepare_spans, text_result_sound

PROJECT = {'labels': ['Person', 'Organisation'], 'label_ontology': []}
AI_SPAN = {'id': 's1', 'label': 'Person', 'geometry_type': 'text_span', 'geometry': {'start': 0, 'end': 9, 'text': 'Anika Rao'},
           'confidence': 0.62, 'source': 'ai', 'model_id': 'gemini', 'provenance': {'capability': 'text_entity_extraction'}}


def test_relabel_keeps_offsets_confidence_and_records_the_ai_label():
    rows = prepare_spans([{**AI_SPAN, 'label': 'Organisation', 'review_status': 'edited'}], [AI_SPAN], PROJECT, 'a', 'p', 40)
    row = rows[0]
    assert row['geometry'] == {'start': 0, 'end': 9, 'text': 'Anika Rao'}
    assert row['text_span'] == {'start': 0, 'end': 9, 'text': 'Anika Rao'}
    assert row['confidence'] == 0.62 and row['review_status'] == 'edited'
    assert row['provenance']['original_ai_label'] == 'Person' and row['provenance']['human_edited']
    assert row['source'] == 'human_modified'


def test_moved_boundary_is_a_correction_and_accepting_is_not():
    moved = prepare_spans([{**AI_SPAN, 'geometry': {'start': 0, 'end': 5, 'text': 'Anika'}, 'review_status': 'edited'}], [AI_SPAN], PROJECT, 'a', 'p', 40)[0]
    assert moved['provenance']['original_ai_span'] == [0, 9] and moved['source'] == 'human_modified'
    kept = prepare_spans([{**AI_SPAN, 'review_status': 'approved'}], [AI_SPAN], PROJECT, 'a', 'p', 40)[0]
    assert kept['source'] == 'ai' and 'original_ai_label' not in kept['provenance'] and kept['review_status'] == 'approved'


def test_new_span_and_document_label_are_accepted():
    rows = prepare_spans([
        {'id': 'n1', 'label': 'Organisation', 'geometry_type': 'text_span', 'geometry': {'start': 20, 'end': 34, 'text': 'Halden Freight'}, 'source': 'human', 'review_status': 'approved'},
        {'id': 'd1', 'label': 'Person', 'geometry_type': 'text_classification', 'geometry': {}, 'source': 'human', 'review_status': 'approved'},
    ], [], PROJECT, 'a', 'p', 40)
    assert [r['geometry_type'] for r in rows] == ['text_span', 'text_classification']
    assert rows[0]['source'] == 'human'


def test_an_ai_label_outside_the_classes_may_be_kept_but_not_introduced():
    stray = {**AI_SPAN, 'label': 'PERSON'}
    assert prepare_spans([{**stray, 'review_status': 'approved'}], [stray], PROJECT, 'a', 'p', 40)[0]['label'] == 'PERSON'
    with pytest.raises(HTTPException):
        prepare_spans([{**AI_SPAN, 'label': 'Vehicle'}], [AI_SPAN], PROJECT, 'a', 'p', 40)


@pytest.mark.parametrize('geometry', [{'start': 5, 'end': 5}, {'start': -1, 'end': 3}, {'start': 30, 'end': 50}, {'start': 'x', 'end': 3}])
def test_bad_offsets_are_refused(geometry):
    with pytest.raises(HTTPException):
        prepare_spans([{**AI_SPAN, 'geometry': geometry}], [AI_SPAN], PROJECT, 'a', 'p', 40)


def test_unknown_decision_and_box_geometry_are_refused():
    with pytest.raises(HTTPException):
        prepare_spans([{**AI_SPAN, 'review_status': 'maybe'}], [AI_SPAN], PROJECT, 'a', 'p', 40)
    with pytest.raises(HTTPException):
        prepare_spans([{**AI_SPAN, 'geometry_type': 'box'}], [AI_SPAN], PROJECT, 'a', 'p', 40)


def test_line_decides_confidence_but_unsound_results_go_to_a_person():
    label = lambda name: {'label': name, 'geometry_type': 'text_classification', 'confidence': 0.74}
    classes = ['Billing', 'Delivery']
    # The model's own 0.95 bar is not the project's line: a clean result is sound.
    assert text_result_sound({'final_decision': 'HUMAN_REVIEW', 'confidence_threshold': 0.95}, [label('Billing')], classes)
    assert not text_result_sound({'errors': ['timeout']}, [label('Billing')], classes)
    assert not text_result_sound({'semantic_conflicts': [{'alternative_label': 'Delivery'}]}, [label('Billing')], classes)
    assert not text_result_sound({'invalid_output': True}, [label('Billing')], classes)
    assert not text_result_sound({}, [], classes)
    assert not text_result_sound({}, [label('Mixed')], ['Positive', 'Neutral', 'Negative'])
