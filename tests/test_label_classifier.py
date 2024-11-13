import pytest
from unittest.mock import patch, MagicMock
from app.controller.label_classifier import get_labels_tree
from app.models.label import Label

@pytest.fixture
def mock_session():
    with patch('app.controller.label_classifier.SessionLocal') as mock:
        yield mock

def test_get_labels_tree_no_labels(mock_session):
    # Mock the session and query
    mock_db = MagicMock()
    mock_db.query().all.return_value = []
    mock_session.return_value.__enter__.return_value = mock_db

    result = get_labels_tree()
    assert result == []

def test_get_labels_tree_single_root(mock_session):
    # Create a single root label
    label = Label(id=1, name='Root', parent_id=None)
    mock_db = MagicMock()
    mock_db.query().all.return_value = [label]
    mock_session.return_value.__enter__.return_value = mock_db

    result = get_labels_tree()
    expected = [{"name": "Root", "children": []}]
    assert result == expected

def test_get_labels_tree_multiple_roots(mock_session):
    # Create multiple root labels
    labels = [
        Label(id=1, name='Root1', parent_id=None),
        Label(id=2, name='Root2', parent_id=None)
    ]
    mock_db = MagicMock()
    mock_db.query().all.return_value = labels
    mock_session.return_value.__enter__.return_value = mock_db

    result = get_labels_tree()
    expected = [
        {"name": "Root1", "children": []},
        {"name": "Root2", "children": []}
    ]
    assert result == expected

def test_get_labels_tree_nested_labels(mock_session):
    # Create nested labels
    labels = [
        Label(id=1, name='Root', parent_id=None),
        Label(id=2, name='Child1', parent_id=1),
        Label(id=3, name='Child2', parent_id=1),
        Label(id=4, name='Grandchild1', parent_id=2)
    ]
    mock_db = MagicMock()
    mock_db.query().all.return_value = labels
    mock_session.return_value.__enter__.return_value = mock_db

    result = get_labels_tree()
    expected = [
        {
            "name": "Root",
            "children": [
                {
                    "name": "Child1",
                    "children": [
                        {"name": "Grandchild1", "children": []}
                    ]
                },
                {
                    "name": "Child2",
                    "children": []
                }
            ]
        }
    ]
    assert result == expected

def test_get_labels_tree_missing_parent(mock_session):
    # Label with a non-existent parent_id
    labels = [
        Label(id=1, name='Orphan', parent_id=999)
    ]
    mock_db = MagicMock()
    mock_db.query().all.return_value = labels
    mock_session.return_value.__enter__.return_value = mock_db

    result = get_labels_tree()
    # Orphan label should not be added to any parent; treated as root
    expected = []
    assert result == expected 