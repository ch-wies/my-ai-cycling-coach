"""Activity data model for storing time-series cycling data"""

from dataclasses import dataclass, field
from typing import Optional
import numpy as np
import pandas as pd


@dataclass
class Activity:
    """Represents a single cycling activity with time-series data"""

    sport: str
    start_time: Optional[str] = None
    total_distance: Optional[float] = None
    total_elapsed_time: Optional[float] = None
    total_moving_time: Optional[float] = None

    # Time-series data stored as pandas DataFrame
    # Columns: timestamp, power, heart_rate, cadence, speed, distance, altitude
    data: pd.DataFrame = field(default_factory=pd.DataFrame)

    def __post_init__(self) -> None:
        if isinstance(self.data, dict):
            self.data = pd.DataFrame(self.data)
        elif not isinstance(self.data, pd.DataFrame):
            self.data = pd.DataFrame()

    def get_time_series(
        self,
        field_name: str,
        start_idx: Optional[int] = None,
        end_idx: Optional[int] = None,
    ) -> np.ndarray:
        if field_name not in self.data.columns:
            return np.array([])

        if start_idx is None:
            start_idx = 0
        if end_idx is None:
            end_idx = len(self.data)

        return np.asarray(self.data.iloc[start_idx:end_idx][field_name].values)

    def get_time_array(
        self, start_idx: Optional[int] = None, end_idx: Optional[int] = None
    ) -> np.ndarray:
        if "timestamp" not in self.data.columns or len(self.data) == 0:
            return np.array([])

        if start_idx is None:
            start_idx = 0
        if end_idx is None:
            end_idx = len(self.data)

        timestamps = self.data.iloc[start_idx:end_idx]["timestamp"].values
        # Convert to seconds from start
        return (timestamps - timestamps[0]).astype("timedelta64[s]").astype(float)

    def get_data_range(self) -> tuple[float, float]:
        if len(self.data) == 0:
            return (0, 0)

        timestamps = self.data["timestamp"].values
        duration = (
            (timestamps[-1] - timestamps[0]).astype("timedelta64[s]").astype(float)
        )
        return (0, duration)

    @property
    def duration_seconds(self) -> float:
        if len(self.data) == 0:
            return 0
        _, end = self.get_data_range()
        return end

    @property
    def available_metrics(self) -> list[str]:
        exclude = {"timestamp"}
        return [col for col in self.data.columns if col not in exclude]
