import pytest
from fastapi.testclient import TestClient
from cortex_api.main import app
from cortex_api.landing_page import FALLBACK_WEBSITE_HTML


@pytest.fixture
def client():
    return TestClient(app)


def test_root_serves_website_html_to_browsers(client):
    """Browsers sending Accept: text/html should receive the visual CORTEX dashboard."""
    response = client.get("/", headers={"Accept": "text/html,application/xhtml+xml"})
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "CORTEX" in response.text


def test_root_serves_json_to_api_clients(client):
    """API clients explicitly sending Accept: application/json should receive JSON health status."""
    response = client.get("/", headers={"Accept": "application/json"})
    assert response.status_code == 200
    assert "application/json" in response.headers.get("content-type", "")
    data = response.json()
    assert data.get("status") == "healthy"
    assert "service" in data


def test_health_endpoints_always_return_json(client):
    """Health endpoints /health and /v1/health should always return pure JSON."""
    res1 = client.get("/health")
    assert res1.status_code == 200
    assert res1.headers.get("content-type", "").startswith("application/json")
    assert res1.json().get("status") in ("healthy", "UP")

    res2 = client.get("/v1/health")
    assert res2.status_code == 200
    assert res2.headers.get("content-type", "").startswith("application/json")
    assert res2.json().get("status") == "healthy"


def test_dashboard_route_serves_html(client):
    """Accessing /dashboard should serve the visual dashboard."""
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "CORTEX" in response.text


def test_spa_subpages_serve_html(client):
    """Subpages like /agents, /analytics, /visitors, /leads should serve HTML."""
    for page in ["/agents", "/analytics", "/visitors", "/leads", "/settings", "/governance"]:
        response = client.get(page)
        assert response.status_code == 200, f"Failed for page {page}"
        assert "text/html" in response.headers.get("content-type", "")


def test_fallback_landing_page_renders():
    """Verify fallback HTML contains key platform elements."""
    assert "CORTEX" in FALLBACK_WEBSITE_HTML
    assert "10-Phase" in FALLBACK_WEBSITE_HTML
    assert "GrowthAgent" in FALLBACK_WEBSITE_HTML
    assert "/docs" in FALLBACK_WEBSITE_HTML
