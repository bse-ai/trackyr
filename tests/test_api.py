"""Tests for API endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from trackyr.api import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_endpoint(client):
    """Health endpoint returns status."""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "db_connected" in data


def test_summary_today(client):
    """Today summary returns expected structure."""
    resp = client.get("/api/v1/summary/today")
    assert resp.status_code == 200
    data = resp.json()
    assert "date" in data
    assert "top_apps" in data
    assert "total_active_seconds" in data


def test_summary_hours(client):
    """Hours summary validates range."""
    resp = client.get("/api/v1/summary/hours/1")
    assert resp.status_code == 200

    resp = client.get("/api/v1/summary/hours/0")
    assert resp.status_code == 400

    resp = client.get("/api/v1/summary/hours/100")
    assert resp.status_code == 400


def test_weekly(client):
    """Weekly endpoint returns 7 days."""
    resp = client.get("/api/v1/weekly")
    assert resp.status_code == 200
    data = resp.json()
    assert "days" in data
    assert len(data["days"]) == 7


def test_categories_crud(client):
    """Categories can be created and listed."""
    # Create
    resp = client.post("/api/v1/categories", json={
        "process_name": "test_app.exe",
        "category": "testing",
        "is_productive": True,
    })
    assert resp.status_code == 200

    # List
    resp = client.get("/api/v1/categories")
    assert resp.status_code == 200
    cats = resp.json()
    assert any(c["process_name"] == "test_app.exe" for c in cats)


def test_goals_crud(client):
    """Goals can be created and listed."""
    resp = client.post("/api/v1/goals", json={
        "name": "Code 4 hours",
        "goal_type": "min_time",
        "target_process": "Code.exe",
        "target_value": 14400,
    })
    assert resp.status_code == 200

    resp = client.get("/api/v1/goals")
    assert resp.status_code == 200
    goals = resp.json()
    assert any(g["name"] == "Code 4 hours" for g in goals)


def test_context_endpoint(client):
    """Context endpoint returns AI-ready data."""
    resp = client.get("/api/v1/context")
    assert resp.status_code == 200
    data = resp.json()
    assert "current_app" in data or "is_idle" in data


def test_search(client):
    """Search endpoint works."""
    resp = client.get("/api/v1/search?q=test")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_trends(client):
    """Trends endpoint returns comparison data."""
    resp = client.get("/api/v1/trends?days=7")
    assert resp.status_code == 200
    data = resp.json()
    assert "change_pct" in data
