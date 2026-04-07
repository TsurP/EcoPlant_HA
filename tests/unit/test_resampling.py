from __future__ import annotations

import pandas as pd

from air_platform.ingestion.resampling import resample_sensor_data


def test_resample_sensor_data_uses_mean_per_device() -> None:
    dataframe = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2024-02-01T00:00:00+00:00",
                    "2024-02-01T00:05:00+00:00",
                    "2024-02-01T00:10:00+00:00",
                    "2024-02-01T00:15:00+00:00",
                ],
                utc=True,
            ),
            "station_id": ["station-1"] * 4,
            "device_id": ["device-1"] * 4,
            "discharge_pressure": [6.0, 8.0, 10.0, 12.0],
        }
    )

    resampled = resample_sensor_data(dataframe, "10min", ["discharge_pressure"])

    assert resampled["discharge_pressure"].tolist() == [7.0, 11.0]
