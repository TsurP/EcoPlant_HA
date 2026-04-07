from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from air_platform.ingestion.models import MissingStrategy, ProcessingConfig
from air_platform.ingestion.pipeline import IngestionPipeline
from air_platform.ingestion.repositories.sqlite import SQLiteSensorDataRepository
from tests.constants import SCHEMA_PATH, TEST_STATION_ID


def test_sqlite_repository_fetches_station_data(test_sensor_db: Path) -> None:
    repository = SQLiteSensorDataRepository(test_sensor_db)

    dataframe = repository.fetch_sensor_readings(
        station_id=TEST_STATION_ID,
        start_time=datetime(2024, 2, 1, tzinfo=UTC),
        end_time=datetime(2024, 2, 1, 3, tzinfo=UTC),
    )
    station = repository.fetch_station_metadata(TEST_STATION_ID)

    assert not dataframe.empty
    assert set(dataframe["station_id"].unique()) == {TEST_STATION_ID}
    assert station is not None
    assert station.station_id == TEST_STATION_ID


def test_ingestion_pipeline_processes_real_station_window(test_sensor_db: Path) -> None:
    pipeline = IngestionPipeline(
        repository=SQLiteSensorDataRepository(test_sensor_db),
        schema_path=SCHEMA_PATH,
    )

    dataset = pipeline.run(
        ProcessingConfig(
            station_id=TEST_STATION_ID,
            start_time=datetime(2024, 2, 1, tzinfo=UTC),
            end_time=datetime(2024, 2, 1, 12, tzinfo=UTC),
            resample_frequency="30min",
            missing_strategy=MissingStrategy.FILL,
            flatline_window_minutes=30,
        )
    )

    assert dataset.rows > 0
    assert dataset.station_metadata is not None
    assert dataset.quality_report.total_rows_read > 0
    assert dataset.cleaning_summary.rows_after_resampling == dataset.rows
    # The test station has multiple compressor devices
    assert len(dataset.device_ids) > 1
