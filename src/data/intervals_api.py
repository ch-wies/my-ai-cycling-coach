"""intervals.icu API client — the app's sole activity data source.

Replaced Strava's API after Strava moved API access behind a paid
subscription. Activity ids here are opaque strings (e.g. "i161859887"), not
bare integers — do not cast them.

Auth is a static personal API key (HTTP Basic, literal username "API_KEY"),
not an OAuth flow, so there is no token-refresh dance to manage. Get your key
and athlete id from intervals.icu -> Settings -> Developer Settings.

Field-name mapping below is based on intervals.icu's published API docs and
community examples (the docs page itself is a JS-rendered Swagger UI that
couldn't be fully introspected offline). The activity-list `id` field shape
has been confirmed against a live response; the per-activity metadata fields
and stream type names (watts/heartrate/cadence/altitude/velocity_smooth/temp)
have NOT been independently verified — check them against a real
download_activity() call and adjust _normalize_activity / _build_activity if
any don't match. `scripts/inspect_activity.py` is a standalone dev script
for exactly this kind of live verification.
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import requests

from .activity import Activity
from src.analysis.activity_metrics import grade_series
from src.constants import INTERVALS_CONFIG_PATH


class IntervalsClientError(Exception):
    """Raised for errors interacting with the intervals.icu API."""


class IntervalsClient:
    """Client for requesting intervals.icu activity metadata and streams."""

    CONFIG_FILE = INTERVALS_CONFIG_PATH
    BASE_URL = "https://intervals.icu/api/v1"
    STREAM_TYPES = "time,watts,heartrate,cadence,distance,altitude,velocity_smooth,temp"

    def __init__(self, api_key: Optional[str] = None, athlete_id: Optional[str] = None):
        config = self._load_config()
        self.api_key = api_key or config.get("api_key")
        self.athlete_id = athlete_id or config.get("athlete_id")
        if not self.api_key or not self.athlete_id:
            raise IntervalsClientError(
                f"Missing intervals.icu credentials. Create {self.CONFIG_FILE} with "
                f'{{"athlete_id": "i123456", "api_key": "..."}} '
                f"(intervals.icu -> Settings -> Developer Settings)."
            )
        self.auth = ("API_KEY", self.api_key)

    def _load_config(self) -> Dict[str, Any]:
        if self.CONFIG_FILE.exists():
            with open(self.CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def list_activities(self, after: datetime) -> List[Dict[str, Any]]:
        params = {"oldest": after.strftime("%Y-%m-%dT%H:%M:%S")}
        try:
            response = requests.get(
                f"{self.BASE_URL}/athlete/{self.athlete_id}/activities",
                auth=self.auth,
                params=params,
                timeout=30,
            )
        except requests.RequestException as e:
            raise IntervalsClientError(
                f"Failed to load intervals.icu activities: {e}"
            ) from e
        if response.status_code != 200:
            raise IntervalsClientError(
                f"Failed to load intervals.icu activities: {response.status_code} {response.text}"
            )
        return [self._normalize_activity(a) for a in response.json()]

    @staticmethod
    def _normalize_activity(raw: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": raw.get("id"),
            "start_date_local": raw.get("start_date_local") or raw.get("start_date"),
            "sport_type": raw.get("type") or raw.get("sport_type") or raw.get("sport"),
            "distance": raw.get("distance"),
            "elapsed_time": raw.get("elapsed_time"),
            "average_watts": raw.get("average_watts") or raw.get("icu_average_watts"),
            "average_heartrate": raw.get("average_heartrate"),
            "trainer": bool(raw.get("trainer")),
        }

    def download_activity(self, activity_id: str) -> Activity:
        metadata = self._get_activity_detail(activity_id)
        streams = self._get_activity_streams(activity_id)
        return self._build_activity(metadata, streams)

    def _get_activity_detail(self, activity_id: str) -> Dict[str, Any]:
        try:
            response = requests.get(
                f"{self.BASE_URL}/activity/{activity_id}",
                auth=self.auth,
                timeout=30,
            )
        except requests.RequestException as e:
            raise IntervalsClientError(f"Failed to fetch activity detail: {e}") from e
        if response.status_code != 200:
            raise IntervalsClientError(
                f"Failed to fetch activity detail: {response.status_code} {response.text}"
            )
        return response.json()

    def _get_activity_streams(self, activity_id: str) -> List[Dict[str, Any]]:
        try:
            response = requests.get(
                f"{self.BASE_URL}/activity/{activity_id}/streams.json",
                auth=self.auth,
                params={"types": self.STREAM_TYPES},
                timeout=30,
            )
        except requests.RequestException as e:
            raise IntervalsClientError(f"Failed to fetch activity streams: {e}") from e
        if response.status_code != 200:
            raise IntervalsClientError(
                f"Failed to fetch activity streams: {response.status_code} {response.text}"
            )
        return response.json()

    def _build_activity(
        self, metadata: Dict[str, Any], streams: List[Dict[str, Any]]
    ) -> Activity:
        start_date = metadata.get("start_date_local") or metadata.get("start_date")
        if not start_date:
            raise IntervalsClientError("Activity metadata is missing start time.")

        start_time = pd.to_datetime(start_date)
        if start_time.tzinfo is not None:
            start_time = start_time.tz_convert(None)

        # Streams arrive as a list of {type, data} objects (like Strava's
        # non-key_by_type format), keyed here by their type for lookup.
        by_type: Dict[str, Any] = {}
        for s in streams:
            stream_type = s.get("type") or s.get("id") or s.get("stream_type")
            if stream_type:
                by_type[stream_type] = s.get("data")

        time_values = by_type.get("time")
        if not time_values:
            raise IntervalsClientError("No time stream available for activity.")

        data = {"timestamp": start_time + pd.to_timedelta(time_values, unit="s")}
        field_mapping = {
            "distance": "distance",
            "altitude": "altitude",
            "heartrate": "heart_rate",
            "cadence": "cadence",
            "watts": "power",
            "velocity_smooth": "speed",
            "temp": "temperature",
        }
        for stream_key, column_name in field_mapping.items():
            values = by_type.get(stream_key)
            if values is not None:
                data[column_name] = values

        # Derived here (data layer calling into analysis) rather than at each
        # consumer, so the UI plot dropdown and the AI tool see the same
        # precomputed column instead of needing two derivation paths.
        if "altitude" in data and "distance" in data:
            time_array = np.asarray(time_values, dtype=float)
            data["grade"] = grade_series(data["altitude"], data["distance"], time_array)

        # No per-sample "moving" stream is mapped (intervals.icu doesn't
        # expose Strava's boolean moving stream); total_moving_time from
        # metadata still lets time_summary() report a moving/stopped split.
        activity = Activity(
            sport=metadata.get("type") or metadata.get("sport_type") or "cycling",
            start_time=start_time,
            total_distance=metadata.get("distance"),
            total_elapsed_time=metadata.get("elapsed_time"),
            total_moving_time=metadata.get("moving_time"),
            data=pd.DataFrame(data),
        )
        return activity
