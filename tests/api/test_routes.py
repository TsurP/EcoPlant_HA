from __future__ import annotations

from fastapi.testclient import TestClient

from air_platform.config import AppSettings
from air_platform.service.app import create_app
from tests.constants import TEST_STATION_ID


def test_health_endpoint(app_settings: AppSettings) -> None:
    client = TestClient(create_app(app_settings))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_process_station_endpoint_happy_path(app_settings: AppSettings) -> None:
    client = TestClient(create_app(app_settings))

    response = client.post(
        f"/stations/{TEST_STATION_ID}/process",
        json={
            "start_time": "2024-02-01T00:00:00+00:00",
            "end_time": "2024-02-01T06:00:00+00:00",
            "resample_frequency": "30min",
            "missing_strategy": "fill",
        },
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["station_id"] == TEST_STATION_ID
    assert payload["metrics_saved"] > 0
    assert payload["devices_processed"] == 3


def test_process_station_endpoint_invalid_station_returns_404(
    app_settings: AppSettings,
) -> None:
    client = TestClient(create_app(app_settings))

    response = client.post("/stations/not-a-station/process", json={})

    assert response.status_code == 404


def test_get_metrics_endpoint_supports_filters(app_settings: AppSettings) -> None:
    client = TestClient(create_app(app_settings))
    process_response = client.post(
        f"/stations/{TEST_STATION_ID}/process",
        json={
            "start_time": "2024-02-01T00:00:00+00:00",
            "end_time": "2024-02-01T06:00:00+00:00",
            "resample_frequency": "30min",
        },
    )
    assert process_response.status_code == 200

    response = client.get(
        "/metrics",
        params={
            "station_id": TEST_STATION_ID,
            "metric_name": "average_pressure_bar",
        },
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload
    assert {item["metric_name"] for item in payload} == {"average_pressure_bar"}
