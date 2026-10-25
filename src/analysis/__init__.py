"""Analysis layer for computing statistics from activity data"""

from .statistics import StatisticsCalculator
from .signal_processing import apply_moving_average_filter
from .activity_metrics import (
    MIN_STOP_S,
    elevation_changes,
    moving_mask,
    normalized_power,
    pedaling_mask,
    representative_dt,
    sample_weights,
    stop_durations,
    time_summary,
    total_work_kj,
    weighted_average,
)

__all__ = [
    "MIN_STOP_S",
    "StatisticsCalculator",
    "apply_moving_average_filter",
    "elevation_changes",
    "moving_mask",
    "normalized_power",
    "pedaling_mask",
    "representative_dt",
    "sample_weights",
    "stop_durations",
    "time_summary",
    "total_work_kj",
    "weighted_average",
]
