"""Tests for src/ai/tools.py"""

import json
from pathlib import Path
from typing import Any, Optional, cast
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd

from src.analysis.activity_metrics import grade_series
from src.data.activity import Activity
from src.ai.tools import (
    _get_activity_details,
    _get_activity_efficiency,
    _get_activity_intervals,
    _get_activity_power_curve,
    _get_activity_training_load,
    _get_activity_zones,
    _list_activities,
    _zone_breakdown,
    execute_tools,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SIMPLE_ZONES = [
    ("Low", 0, 50),
    ("High", 50, None),
]


def _make_activity(power: Any = None, heart_rate: Any = None, n: int = 100) -> Any:
    activity = Mock()
    activity.get_time_array.return_value = np.arange(n, dtype=float)

    def _series(metric: str) -> Any:
        if metric == "power":
            return power
        if metric == "heart_rate":
            return heart_rate
        return None

    activity.get_time_series.side_effect = _series
    return activity


def _real_activity(
    n: int = 600,
    dt: float = 1.0,
    power: Any = 200.0,
    heart_rate: Any = 150.0,
    cadence: Any = 85.0,
    speed: Any = 8.0,
    altitude: Any = None,
    temperature: Any = None,
    sport: str = "Ride",
    elapsed: Optional[float] = None,
    moving_time: Optional[float] = None,
) -> Activity:
    # Unlike _make_activity (a Mock), this builds a real Activity — needed for
    # tests that exercise actual DataFrame-backed behavior, not just call routing.
    cols: dict[str, Any] = {
        "timestamp": pd.to_datetime(0, unit="s")
        + pd.to_timedelta(np.arange(n) * dt, unit="s")
    }

    def _col(val: float | np.ndarray) -> np.ndarray:
        return (
            np.asarray(val, dtype=float)
            if not np.isscalar(val)
            else np.full(n, float(cast(Any, val)))
        )

    if power is not None:
        cols["power"] = _col(power)
    if heart_rate is not None:
        cols["heart_rate"] = _col(heart_rate)
    if cadence is not None:
        cols["cadence"] = _col(cadence)
    if speed is not None:
        cols["speed"] = _col(speed)
    if altitude is not None:
        cols["altitude"] = _col(altitude)
    if temperature is not None:
        cols["temperature"] = _col(temperature)
    cols["distance"] = np.cumsum(_col(speed if speed is not None else 8.0)) * dt
    if altitude is not None:
        # Mirrors IntervalsClient._build_activity, which precomputes grade
        # once at Activity-build time rather than at each consumer.
        time_array = np.arange(n, dtype=float) * dt
        cols["grade"] = grade_series(cols["altitude"], cols["distance"], time_array)
    return Activity(
        sport=sport,
        total_elapsed_time=elapsed if elapsed is not None else (n - 1) * dt,
        total_moving_time=moving_time,
        data=pd.DataFrame(cols),
    )


def _make_block(name: str, **inputs: Any) -> Any:
    block = Mock()
    block.type = "tool_use"
    block.id = "block_001"
    block.name = name
    block.input = inputs
    return block


# ---------------------------------------------------------------------------
# execute_tools
# ---------------------------------------------------------------------------


class TestExecuteTools:
    def test_empty_content_returns_empty(self) -> None:
        assert execute_tools([], Mock()) == []

    def test_non_tool_block_skipped(self) -> None:
        block = Mock()
        block.type = "text"
        assert execute_tools([block], Mock()) == []

    def test_block_without_type_attr_skipped(self) -> None:
        assert execute_tools(cast(list, [object()]), Mock()) == []

    def test_result_structure(self) -> None:
        block = _make_block("list_recent_activities", weeks=4)
        with patch("src.ai.tools._list_activities", return_value="output"):
            results = execute_tools([block], Mock())
        assert results == [
            {"type": "tool_result", "tool_use_id": "block_001", "content": "output"}
        ]

    def test_routes_list_recent_activities(self) -> None:
        block = _make_block("list_recent_activities", weeks=4)
        with patch("src.ai.tools._list_activities", return_value="ok") as fn:
            execute_tools([block], Mock())
        fn.assert_called_once()

    def test_routes_get_activity_details(self) -> None:
        block = _make_block("get_activity_details", activity_id=1)
        with patch("src.ai.tools._get_activity_details", return_value="ok") as fn:
            execute_tools([block], Mock())
        fn.assert_called_once()

    def test_routes_get_activity_power_curve(self) -> None:
        block = _make_block("get_activity_power_curve", activity_id=1)
        with patch("src.ai.tools._get_activity_power_curve", return_value="ok") as fn:
            execute_tools([block], Mock())
        fn.assert_called_once()

    def test_routes_get_activity_zones(self) -> None:
        block = _make_block("get_activity_zones", activity_id=1)
        with patch("src.ai.tools._get_activity_zones", return_value="ok") as fn:
            execute_tools([block], Mock())
        fn.assert_called_once()

    def test_routes_get_activity_training_load(self) -> None:
        block = _make_block("get_activity_training_load", activity_id=1)
        with patch("src.ai.tools._get_activity_training_load", return_value="ok") as fn:
            execute_tools([block], Mock())
        fn.assert_called_once()

    def test_routes_get_activity_efficiency(self) -> None:
        block = _make_block("get_activity_efficiency", activity_id=1)
        with patch("src.ai.tools._get_activity_efficiency", return_value="ok") as fn:
            execute_tools([block], Mock())
        fn.assert_called_once()

    def test_routes_get_activity_intervals(self) -> None:
        block = _make_block("get_activity_intervals", activity_id=1)
        with patch("src.ai.tools._get_activity_intervals", return_value="ok") as fn:
            execute_tools([block], Mock())
        fn.assert_called_once()

    def test_unknown_tool_returns_error_string(self) -> None:
        block = _make_block("no_such_tool")
        results = execute_tools([block], Mock())
        assert "Unknown tool" in results[0]["content"]

    def test_multiple_blocks_all_processed(self) -> None:
        blocks = [
            _make_block("list_recent_activities", weeks=4),
            _make_block("get_activity_details", activity_id=1),
        ]
        with (
            patch("src.ai.tools._list_activities", return_value="a"),
            patch("src.ai.tools._get_activity_details", return_value="b"),
        ):
            results = execute_tools(blocks, Mock())
        assert len(results) == 2


# ---------------------------------------------------------------------------
# _list_activities
# ---------------------------------------------------------------------------


class TestListActivities:
    def test_empty_returns_no_activities_message(self) -> None:
        client = Mock()
        client.list_activities.return_value = []
        assert "No activities found" in _list_activities(client, 4)
        assert "4 weeks" in _list_activities(client, 4)

    def test_weeks_clamped_to_minimum_1(self) -> None:
        client = Mock()
        client.list_activities.return_value = []
        result = _list_activities(client, 0)
        assert "1 weeks" in result

    def test_weeks_clamped_to_maximum_52(self) -> None:
        client = Mock()
        client.list_activities.return_value = []
        assert "52 weeks" in _list_activities(client, 100)

    def test_basic_activity_format(self) -> None:
        client = Mock()
        client.list_activities.return_value = [
            {
                "id": 123,
                "start_date_local": "2024-01-15T10:00:00Z",
                "sport_type": "Ride",
                "distance": 50000,
                "elapsed_time": 7200,
            }
        ]
        result = _list_activities(client, 4)
        assert "ID 123" in result
        assert "2024-01-15" in result
        assert "Ride" in result
        assert "50.0 km" in result
        assert "2h00m" in result

    def test_optional_power_and_hr_included_when_present(self) -> None:
        client = Mock()
        client.list_activities.return_value = [
            {
                "id": 1,
                "start_date_local": "",
                "sport_type": "Ride",
                "distance": 0,
                "elapsed_time": 0,
                "average_watts": 245.6,
                "average_heartrate": 152.3,
            }
        ]
        result = _list_activities(client, 4)
        assert "246 W avg" in result
        assert "152 bpm avg" in result

    def test_optional_power_and_hr_absent_when_missing(self) -> None:
        client = Mock()
        client.list_activities.return_value = [
            {
                "id": 1,
                "start_date_local": "",
                "sport_type": "Run",
                "distance": 10000,
                "elapsed_time": 3600,
            }
        ]
        result = _list_activities(client, 4)
        assert "W avg" not in result
        assert "bpm avg" not in result


# ---------------------------------------------------------------------------
# _get_activity_details
# ---------------------------------------------------------------------------


class TestGetActivityDetails:
    def test_success_formats_sections(self) -> None:
        client = Mock()
        client.download_activity.return_value = _real_activity(
            n=600, power=200.0, heart_rate=150.0, moving_time=590
        )
        result = _get_activity_details(client, "42")
        assert "Activity 42 details:" in result
        assert "Sport: Ride" in result
        assert "Time:" in result
        assert "Elapsed:" in result
        assert "Moving:" in result
        assert "Max power: 200 W" in result

    def test_dual_averages_when_speed_present(self) -> None:
        client = Mock()
        client.download_activity.return_value = _real_activity(n=300, power=180.0)
        result = _get_activity_details(client, "42")
        assert "Averages (moving | full):" in result
        # constant 180 W → both columns equal
        assert "Power: 180 | 180 W" in result

    def test_single_average_when_no_speed(self) -> None:
        client = Mock()
        client.download_activity.return_value = _real_activity(
            n=300, power=180.0, speed=None
        )
        result = _get_activity_details(client, "42")
        assert "Averages:" in result
        assert "Moving: unavailable (no moving time or speed stream)" in result

    def test_zero_speed_stretch_is_a_stop(self) -> None:
        speed = np.concatenate([np.full(200, 8.0), np.zeros(60), np.full(200, 8.0)])
        power = np.concatenate([np.full(200, 200.0), np.zeros(60), np.full(200, 200.0)])
        client = Mock()
        client.download_activity.return_value = _real_activity(
            n=460, power=power, speed=speed
        )
        result = _get_activity_details(client, "42")
        assert "Averages (moving | full):" in result
        assert "(1 stop)" in result
        # stopped samples (0 W) only drag down the full average
        assert "Power: 200 | 174 W" in result

    def test_pedalling_power_excludes_coasting(self) -> None:
        # First half pedalling at 200 W, second half coasting (0 W, cadence 0)
        power = np.concatenate([np.full(300, 200.0), np.full(300, 0.0)])
        cadence = np.concatenate([np.full(300, 85.0), np.full(300, 0.0)])
        client = Mock()
        client.download_activity.return_value = _real_activity(
            n=600, power=power, cadence=cadence, heart_rate=None
        )
        result = _get_activity_details(client, "42")
        assert "Pedalling:" in result
        # moving avg is ~100 W (half coasting); pedalling-only is ~200 W
        assert "Power (pedalling): 200 W" in result
        assert "Power: 100 | 100 W" in result
        assert "Coasting: 50% of moving time" in result

    def test_elevation_reported_when_altitude_present(self) -> None:
        # climb 0→100 m then descend back to 0
        alt = np.concatenate([np.linspace(0, 100, 150), np.linspace(100, 0, 150)])
        client = Mock()
        client.download_activity.return_value = _real_activity(n=300, altitude=alt)
        result = _get_activity_details(client, "42")
        assert "Elevation:" in result
        assert "Ascent:" in result
        assert "Descent:" in result

    def test_elevation_absent_without_altitude(self) -> None:
        client = Mock()
        client.download_activity.return_value = _real_activity(n=300, altitude=None)
        result = _get_activity_details(client, "42")
        assert "Elevation:" not in result
        assert "Max grade" not in result

    @staticmethod
    def _line_value(result: str, label: str) -> str:
        line = next(ln for ln in result.splitlines() if ln.strip().startswith(label))
        return line.split(label, 1)[1].strip()

    def test_climbing_metrics_reported_for_real_climb(self) -> None:
        # flat, then a steady 10% climb (80 m rise over 800 m run), then flat —
        # keeps the smoothing window's edge effects away from the interior of
        # the climb so the reported grade stays close to the true 10%.
        flat_start = np.zeros(100)
        climb = np.linspace(0, 80, 100)
        flat_end = np.full(100, 80.0)
        alt = np.concatenate([flat_start, climb, flat_end])
        client = Mock()
        client.download_activity.return_value = _real_activity(
            n=300, altitude=alt, speed=8.0
        )
        result = _get_activity_details(client, "42")

        max_grade = float(self._line_value(result, "Max grade:").rstrip("%"))
        assert 5 < max_grade < 15
        avg_grade = float(self._line_value(result, "Avg grade (climbing):").rstrip("%"))
        assert 5 < avg_grade < 15
        assert "Climbing time:" in result
        assert self._line_value(result, "Climbing time:") != "0m00s (grade > 3%)"
        ascent_line = self._line_value(result, "Ascent:")
        assert "m/km)" in ascent_line

    def test_climbing_lines_omitted_below_threshold(self) -> None:
        # a steady ~2% grade for the whole ride — never crosses the 3% threshold
        alt = np.linspace(0, 48, 300)
        client = Mock()
        client.download_activity.return_value = _real_activity(
            n=300, altitude=alt, speed=8.0
        )
        result = _get_activity_details(client, "42")

        max_grade = float(self._line_value(result, "Max grade:").rstrip("%"))
        assert max_grade < 3
        assert "Avg grade (climbing):" not in result
        assert "Climbing time:" not in result
        assert "m/km)" in self._line_value(result, "Ascent:")

    def test_ascent_per_km_stays_large_for_a_loop(self) -> None:
        # start/end altitude equal (net elevation change ~0), but a real
        # intermediate hill — ascent per km should stay large and nonzero,
        # unlike a global/net average grade which would cancel to ~0 here.
        alt = np.concatenate([np.linspace(0, 100, 150), np.linspace(100, 0, 150)])
        client = Mock()
        client.download_activity.return_value = _real_activity(
            n=300, altitude=alt, speed=8.0
        )
        result = _get_activity_details(client, "42")

        ascent_line = self._line_value(result, "Ascent:")
        m_per_km = float(ascent_line.split("(")[1].split(" m/km")[0])
        assert m_per_km > 20

    def test_download_error_returns_error_message(self) -> None:
        client = Mock()
        client.download_activity.side_effect = Exception("timeout")
        result = _get_activity_details(client, "42")
        assert "Failed to download activity 42" in result
        assert "timeout" in result

    def test_temperature_line_present_when_series_available(self) -> None:
        client = Mock()
        client.download_activity.return_value = _real_activity(n=300, temperature=19.0)
        result = _get_activity_details(client, "42")
        assert "Temperature: 19 | 19 °C" in result

    def test_temperature_line_absent_when_series_missing(self) -> None:
        client = Mock()
        client.download_activity.return_value = _real_activity(n=300, temperature=None)
        result = _get_activity_details(client, "42")
        assert "Temperature" not in result

    def test_temperature_range_shown_when_values_vary(self) -> None:
        client = Mock()
        temps = np.concatenate([np.full(150, 15.0), np.full(150, 25.0)])
        client.download_activity.return_value = _real_activity(n=300, temperature=temps)
        result = _get_activity_details(client, "42")
        assert "Temperature: 20 | 20 °C (15–25°C range)" in result

    def test_temperature_range_omitted_when_constant(self) -> None:
        client = Mock()
        client.download_activity.return_value = _real_activity(n=300, temperature=19.0)
        result = _get_activity_details(client, "42")
        assert "Temperature: 19 | 19 °C" in result
        assert "range" not in result


# ---------------------------------------------------------------------------
# _get_activity_power_curve
# ---------------------------------------------------------------------------


class TestGetActivityPowerCurve:
    def test_success_contains_header_and_values(self) -> None:
        power = np.full(500, 250.0)
        client = Mock()
        client.download_activity.return_value = _make_activity(power=power, n=500)
        result = _get_activity_power_curve(client, "42")
        assert "Activity 42 power curve:" in result
        assert "5s:" in result
        assert "250 W" in result

    def test_no_power_data_returns_message(self) -> None:
        client = Mock()
        client.download_activity.return_value = _make_activity(power=np.array([]))
        result = _get_activity_power_curve(client, "42")
        assert "No power data available for activity 42" in result

    def test_download_error_returns_error_message(self) -> None:
        client = Mock()
        client.download_activity.side_effect = Exception("timeout")
        result = _get_activity_power_curve(client, "42")
        assert "Failed to download activity 42" in result


# ---------------------------------------------------------------------------
# _get_activity_training_load
# ---------------------------------------------------------------------------


class TestGetActivityTrainingLoad:
    def test_no_power_returns_message(self, tmp_path: Path) -> None:
        client = Mock()
        client.download_activity.return_value = _real_activity(n=100, power=None)
        with patch("src.goals.GOALS_PATH", tmp_path / "goals.json"):
            result = _get_activity_training_load(client, "42")
        assert "needs power" in result

    def test_core_metrics_without_goals(self, tmp_path: Path) -> None:
        client = Mock()
        client.download_activity.return_value = _real_activity(n=600, power=200.0)
        with patch("src.goals.GOALS_PATH", tmp_path / "missing.json"):
            result = _get_activity_training_load(client, "42")
        assert "Normalized Power: 200 W" in result  # constant power → NP == avg
        assert "Variability Index: 1.00" in result
        assert "Work:" in result
        assert "kcal (rough estimate)" in result
        assert "set FTP in Training Goals" in result

    def test_ftp_enables_if_and_tss(self, tmp_path: Path) -> None:
        goals = tmp_path / "goals.json"
        goals.write_text(json.dumps({"current_ftp_watts": 250}))
        client = Mock()
        client.download_activity.return_value = _real_activity(n=3600, power=250.0)
        with patch("src.goals.GOALS_PATH", goals):
            result = _get_activity_training_load(client, "42")
        assert "Intensity Factor: 1.00 (FTP 250 W)" in result
        # 1 h at FTP → ~100 TSS
        assert "TSS: 100" in result

    def test_weight_enables_power_to_weight(self, tmp_path: Path) -> None:
        goals = tmp_path / "goals.json"
        goals.write_text(json.dumps({"weight_kg": 70}))
        client = Mock()
        client.download_activity.return_value = _real_activity(n=600, power=210.0)
        with patch("src.goals.GOALS_PATH", goals):
            result = _get_activity_training_load(client, "42")
        assert "3.00 W/kg" in result

    def test_efficiency_factor_with_hr(self, tmp_path: Path) -> None:
        client = Mock()
        client.download_activity.return_value = _real_activity(
            n=600, power=200.0, heart_rate=160.0
        )
        with patch("src.goals.GOALS_PATH", tmp_path / "missing.json"):
            result = _get_activity_training_load(client, "42")
        assert "Efficiency Factor: 1.25 W/beat" in result

    def test_download_error_returns_error(self) -> None:
        client = Mock()
        client.download_activity.side_effect = Exception("timeout")
        assert "Failed to download activity 42" in _get_activity_training_load(
            client, "42"
        )


# ---------------------------------------------------------------------------
# _get_activity_efficiency
# ---------------------------------------------------------------------------


class TestGetActivityEfficiency:
    def test_decoupling_and_splits_present(self) -> None:
        client = Mock()
        client.download_activity.return_value = _real_activity(
            n=600, power=200.0, heart_rate=150.0
        )
        result = _get_activity_efficiency(client, "42")
        assert "Aerobic decoupling (Pw:Hr):" in result
        assert "Splits (first half | second half):" in result
        assert "Power: 200 W | 200 W" in result

    def test_positive_decoupling_when_hr_drifts_up(self) -> None:
        # power steady, HR rises in second half → power:HR ratio falls → positive drift
        hr = np.concatenate([np.full(300, 140.0), np.full(300, 160.0)])
        client = Mock()
        client.download_activity.return_value = _real_activity(
            n=600, power=200.0, heart_rate=hr
        )
        result = _get_activity_efficiency(client, "42")
        assert "+" in result.split("Pw:Hr):")[1].split("%")[0]

    def test_missing_hr_notes_requirement(self) -> None:
        client = Mock()
        client.download_activity.return_value = _real_activity(
            n=600, power=200.0, heart_rate=None
        )
        result = _get_activity_efficiency(client, "42")
        assert "needs both power and heart rate" in result

    def test_download_error_returns_error(self) -> None:
        client = Mock()
        client.download_activity.side_effect = Exception("timeout")
        assert "Failed to download activity 42" in _get_activity_efficiency(
            client, "42"
        )


class TestGetActivityIntervals:
    def _activity_with_block(self, n: int = 1500, hr_drift: bool = False) -> Activity:
        power = np.full(n, 100.0)
        power[600:1000] = 300.0  # 400 s block at 300 W (1.2x a 250 W FTP)
        hr = np.full(n, 140.0)
        if hr_drift:
            hr[600:1000] = np.linspace(150, 175, 400)
        return _real_activity(n=n, power=power, heart_rate=hr, cadence=90.0)

    def test_detects_and_reports_execution(self, tmp_path: Path) -> None:
        goals = tmp_path / "goals.json"
        goals.write_text(json.dumps({"current_ftp_watts": 250}))
        client = Mock()
        client.download_activity.return_value = self._activity_with_block(hr_drift=True)
        with patch("src.goals.GOALS_PATH", goals):
            result = _get_activity_intervals(client, "42")
        assert "1 structured work interval" in result
        assert "Interval 1:" in result
        assert "FTP 250 W" in result
        assert "% FTP)" in result
        assert "HR " in result and "→" in result  # start->end drift reported
        assert "rpm" in result
        assert (
            "HRR60" in result
        )  # recovery-window power (100 W) backs off well below FTP

    def test_contaminated_by_next_interval_omits_hrr60(self, tmp_path: Path) -> None:
        goals = tmp_path / "goals.json"
        goals.write_text(json.dumps({"current_ftp_watts": 250}))
        n = 1500
        power = np.full(n, 100.0)
        power[100:400] = 300.0  # interval 1: 300 s @ 300 W
        power[450:750] = 300.0  # interval 2 starts 50 s after interval 1 ends
        hr = np.full(n, 140.0)
        hr[100:400] = 170.0
        hr[450:750] = 170.0
        activity = _real_activity(n=n, power=power, heart_rate=hr, cadence=90.0)
        client = Mock()
        client.download_activity.return_value = activity
        with patch("src.goals.GOALS_PATH", goals):
            result = _get_activity_intervals(client, "42")
        lines = {
            line.split(":")[0].strip(): line
            for line in result.splitlines()
            if line.strip().startswith("Interval")
        }
        assert "Interval 1" in lines and "Interval 2" in lines
        assert "HRR60" not in lines["Interval 1"]
        assert "HRR60" in lines["Interval 2"]

    def test_insufficient_trailing_data_omits_hrr60(self, tmp_path: Path) -> None:
        goals = tmp_path / "goals.json"
        goals.write_text(json.dumps({"current_ftp_watts": 250}))
        n = 450
        power = np.full(n, 100.0)
        power[100:400] = 300.0  # interval ends ~50 s before recording ends
        hr = np.full(n, 140.0)
        hr[100:400] = 170.0
        activity = _real_activity(n=n, power=power, heart_rate=hr, cadence=90.0)
        client = Mock()
        client.download_activity.return_value = activity
        with patch("src.goals.GOALS_PATH", goals):
            result = _get_activity_intervals(client, "42")
        assert "Interval 1:" in result
        assert "HRR60" not in result

    def test_sustained_power_during_recovery_omits_hrr60(self, tmp_path: Path) -> None:
        goals = tmp_path / "goals.json"
        goals.write_text(json.dumps({"current_ftp_watts": 250}))
        n = 1500
        power = np.full(n, 100.0)
        power[600:1000] = 300.0  # interval: 400 s @ 300 W
        power[1000:1060] = 200.0  # 80% FTP recovery window — rider kept working
        hr = np.full(n, 140.0)
        hr[600:1000] = np.linspace(150, 175, 400)  # HR still drops after the effort
        activity = _real_activity(n=n, power=power, heart_rate=hr, cadence=90.0)
        client = Mock()
        client.download_activity.return_value = activity
        with patch("src.goals.GOALS_PATH", goals):
            result = _get_activity_intervals(client, "42")
        assert "Interval 1:" in result
        assert "HRR60" not in result

    def test_no_intervals_when_flat(self, tmp_path: Path) -> None:
        goals = tmp_path / "goals.json"
        goals.write_text(json.dumps({"current_ftp_watts": 250}))
        client = Mock()
        client.download_activity.return_value = _real_activity(n=600, power=100.0)
        with patch("src.goals.GOALS_PATH", goals):
            result = _get_activity_intervals(client, "42")
        assert "No structured work intervals" in result

    def test_no_power_returns_message(self, tmp_path: Path) -> None:
        client = Mock()
        client.download_activity.return_value = _real_activity(n=300, power=None)
        with patch("src.goals.GOALS_PATH", tmp_path / "missing.json"):
            result = _get_activity_intervals(client, "42")
        assert "No power data" in result

    def test_no_ftp_omits_percent(self, tmp_path: Path) -> None:
        client = Mock()
        client.download_activity.return_value = self._activity_with_block()
        with patch("src.goals.GOALS_PATH", tmp_path / "missing.json"):
            result = _get_activity_intervals(client, "42")
        assert "no FTP set" in result
        assert "% FTP)" not in result

    def test_download_error_returns_error(self) -> None:
        client = Mock()
        client.download_activity.side_effect = Exception("timeout")
        assert "Failed to download activity 42" in _get_activity_intervals(client, "42")


# ---------------------------------------------------------------------------
# _zone_breakdown
# ---------------------------------------------------------------------------


class TestZoneBreakdown:
    def test_returns_one_line_per_zone(self) -> None:
        series = np.full(60, 100.0)
        lines = _zone_breakdown(series, _SIMPLE_ZONES, 200, 1.0)
        assert len(lines) == len(_SIMPLE_ZONES)

    def test_all_samples_in_low_zone(self) -> None:
        series = np.full(60, 50.0)  # 25% of reference 200 → Low
        lines = _zone_breakdown(series, _SIMPLE_ZONES, 200, 1.0)
        assert "100.0%" in lines[0]
        assert "0.0%" in lines[1]

    def test_all_samples_in_open_ended_top_zone(self) -> None:
        series = np.full(60, 150.0)  # 75% of reference 200 → High (no upper bound)
        lines = _zone_breakdown(series, _SIMPLE_ZONES, 200, 1.0)
        assert "0.0%" in lines[0]
        assert "100.0%" in lines[1]

    def test_nan_values_excluded_from_total(self) -> None:
        series = np.array([50.0] * 30 + [np.nan] * 30)
        lines = _zone_breakdown(series, _SIMPLE_ZONES, 200, 1.0)
        # 30 valid samples all in Low → 100%, not 50%
        assert "100.0%" in lines[0]

    def test_dt_scaling(self) -> None:
        series = np.full(30, 50.0)  # 30 samples × dt=2.0 → 60 s
        lines = _zone_breakdown(series, _SIMPLE_ZONES, 200, 2.0)
        assert "1m00s" in lines[0]

    def test_sub_hour_time_format(self) -> None:
        series = np.full(90, 50.0)  # 90 s → 1m30s
        lines = _zone_breakdown(series, _SIMPLE_ZONES, 200, 1.0)
        assert "1m30s" in lines[0]

    def test_over_hour_time_format(self) -> None:
        series = np.full(3661, 50.0)  # 3661 s → 1h01m01s
        lines = _zone_breakdown(series, _SIMPLE_ZONES, 200, 1.0)
        assert "1h01m01s" in lines[0]

    def test_zero_valid_samples_all_zero_percent(self) -> None:
        series = np.full(10, np.nan)
        lines = _zone_breakdown(series, _SIMPLE_ZONES, 200, 1.0)
        for line in lines:
            assert "0.0%" in line


# ---------------------------------------------------------------------------
# _get_activity_zones
# ---------------------------------------------------------------------------


class TestGetActivityZones:
    def test_goals_unreadable_returns_error(self, tmp_path: Path) -> None:
        with patch("src.ai.tools.GOALS_PATH", tmp_path / "missing.json"):
            result = _get_activity_zones(Mock(), "42")
        assert "Training goals not available" in result

    def test_neither_ftp_nor_max_hr_returns_error(self, tmp_path: Path) -> None:
        goals = tmp_path / "goals.json"
        goals.write_text(json.dumps({}))
        with patch("src.ai.tools.GOALS_PATH", goals):
            result = _get_activity_zones(Mock(), "42")
        assert "Neither FTP nor max heart rate" in result

    def test_download_error_returns_error(self, tmp_path: Path) -> None:
        goals = tmp_path / "goals.json"
        goals.write_text(json.dumps({"current_ftp_watts": 280}))
        client = Mock()
        client.download_activity.side_effect = Exception("timeout")
        with patch("src.ai.tools.GOALS_PATH", goals):
            result = _get_activity_zones(client, "42")
        assert "Failed to download activity 42" in result

    def test_only_ftp_power_zones_computed_hr_skipped(self, tmp_path: Path) -> None:
        goals = tmp_path / "goals.json"
        goals.write_text(json.dumps({"current_ftp_watts": 280}))
        client = Mock()
        client.download_activity.return_value = _make_activity(
            power=np.full(100, 200.0)
        )
        with patch("src.ai.tools.GOALS_PATH", goals):
            result = _get_activity_zones(client, "42")
        assert "Power zones (Coggan, FTP = 280 W):" in result
        assert "set max heart rate in Training Goals" in result

    def test_only_max_hr_hr_zones_computed_power_skipped(self, tmp_path: Path) -> None:
        goals = tmp_path / "goals.json"
        goals.write_text(json.dumps({"max_hr_bpm": 185}))
        client = Mock()
        client.download_activity.return_value = _make_activity(
            heart_rate=np.full(100, 150.0)
        )
        with patch("src.ai.tools.GOALS_PATH", goals):
            result = _get_activity_zones(client, "42")
        assert "set FTP in Training Goals" in result
        assert "HR zones (max HR = 185 bpm):" in result

    def test_both_set_both_sections_present(self, tmp_path: Path) -> None:
        goals = tmp_path / "goals.json"
        goals.write_text(json.dumps({"current_ftp_watts": 280, "max_hr_bpm": 185}))
        client = Mock()
        client.download_activity.return_value = _make_activity(
            power=np.full(100, 200.0), heart_rate=np.full(100, 150.0)
        )
        with patch("src.ai.tools.GOALS_PATH", goals):
            result = _get_activity_zones(client, "42")
        assert "Power zones (Coggan, FTP = 280 W):" in result
        assert "HR zones (max HR = 185 bpm):" in result

    def test_ftp_set_but_no_power_data(self, tmp_path: Path) -> None:
        goals = tmp_path / "goals.json"
        goals.write_text(json.dumps({"current_ftp_watts": 280}))
        client = Mock()
        client.download_activity.return_value = _make_activity(power=np.array([]))
        with patch("src.ai.tools.GOALS_PATH", goals):
            result = _get_activity_zones(client, "42")
        assert "Power zones: no power data" in result

    def test_max_hr_set_but_no_hr_data(self, tmp_path: Path) -> None:
        goals = tmp_path / "goals.json"
        goals.write_text(json.dumps({"max_hr_bpm": 185}))
        client = Mock()
        client.download_activity.return_value = _make_activity(heart_rate=np.array([]))
        with patch("src.ai.tools.GOALS_PATH", goals):
            result = _get_activity_zones(client, "42")
        assert "HR zones: no heart rate data" in result

    def test_reference_values_visible_in_headers(self, tmp_path: Path) -> None:
        goals = tmp_path / "goals.json"
        goals.write_text(json.dumps({"current_ftp_watts": 300, "max_hr_bpm": 190}))
        client = Mock()
        client.download_activity.return_value = _make_activity(
            power=np.full(100, 200.0), heart_rate=np.full(100, 150.0)
        )
        with patch("src.ai.tools.GOALS_PATH", goals):
            result = _get_activity_zones(client, "42")
        assert "FTP = 300 W" in result
        assert "max HR = 190 bpm" in result
