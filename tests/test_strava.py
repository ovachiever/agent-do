#!/usr/bin/env python3
import importlib.machinery, json, os, subprocess, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "agent-strava"
strava = importlib.machinery.SourceFileLoader("agent_strava", str(TOOL)).load_module()

def run(*args, env=None):
    return subprocess.run([str(TOOL), *args], text=True, capture_output=True, env=env)

def test_status_without_profile():
    with tempfile.TemporaryDirectory() as home:
        result = run("status", env={**os.environ, "AGENT_DO_HOME": home})
        assert result.returncode == 0 and "No local Strava profile" in result.stdout

def test_status_json_without_profile_is_machine_readable():
    with tempfile.TemporaryDirectory() as home:
        result = run("status", "--json", env={**os.environ, "AGENT_DO_HOME": home})
        assert result.returncode == 0
        assert json.loads(result.stdout) == {"configured": False, "cache_present": False, "next_command": "agent-do strava init"}

def test_profile_units_are_local_configuration():
    with tempfile.TemporaryDirectory() as home:
        data = Path(home) / "strava"; data.mkdir()
        (data / "profile.json").write_text(json.dumps({"athlete_name": "Test", "units": "metric"}))
        result = run("status", "--json", env={**os.environ, "AGENT_DO_HOME": home})
        assert result.returncode == 0 and json.loads(result.stdout)["units"] == "metric"

def test_dashboard_uses_local_cache_only():
    with tempfile.TemporaryDirectory() as home:
        data = Path(home) / "strava"; data.mkdir()
        (data / "activities.json").write_text(json.dumps({"synced_at": "2026-09-06T00:00:00+00:00", "activities": []}))
        result = run("dashboard", env={**os.environ, "AGENT_DO_HOME": home})
        assert result.returncode == 0
        page = Path(result.stdout.strip())
        assert page.exists() and "Your training" in page.read_text()

def test_summary_calculates_selected_range():
    now = strava.datetime.now(strava.timezone.utc)
    activities = [
        {"start_date": (now - strava.timedelta(days=2)).isoformat(), "distance": 5000, "moving_time": 1800, "total_elevation_gain": 100},
        {"start_date": (now - strava.timedelta(days=10)).isoformat(), "distance": 9000, "moving_time": 3600, "total_elevation_gain": 200},
    ]
    result = strava.summarize(activities, days=7)
    assert result["distance_km"] == 5 and result["moving_minutes"] == 30 and result["activity_count"] == 1
    assert result["weekly"] and result["weekly"][0]["distance_km"] == 5

def test_summary_filters_by_specific_strava_sport_type():
    now = strava.datetime.now(strava.timezone.utc)
    activities = [
        {"start_date": (now - strava.timedelta(days=1)).isoformat(), "sport_type": "TrailRun", "type": "Run", "distance": 5000},
        {"start_date": (now - strava.timedelta(days=1)).isoformat(), "sport_type": "Ride", "type": "Ride", "distance": 12000},
    ]
    result = strava.summarize(activities, days=7, activity_type="TrailRun")
    assert result["activity_count"] == 1 and result["distance_km"] == 5
    assert strava.activity_kind({"sport_type": "WeightTraining"}) == "WeightTraining"

def test_responsive_dashboard_uses_manual_sync_without_polling():
    assert "/api/sync" in strava.DYNAMIC_DASHBOARD
    assert "/api/preferences" in strava.DYNAMIC_DASHBOARD
    assert "activity-type" in strava.DYNAMIC_DASHBOARD
    assert "activity_types" in strava.DYNAMIC_DASHBOARD
    assert "activity-heading" in strava.DYNAMIC_DASHBOARD
    assert "friendly" in strava.DYNAMIC_DASHBOARD
    assert "Date &amp; time" in strava.DYNAMIC_DASHBOARD
    assert "WeightTraining'?'--'" in strava.DYNAMIC_DASHBOARD
    assert "setInterval" not in strava.DYNAMIC_DASHBOARD
    assert "localStorage" not in strava.DYNAMIC_DASHBOARD
    assert "Units: Imperial" in strava.DYNAMIC_DASHBOARD
    assert "Distance per week" in strava.DYNAMIC_DASHBOARD
    assert "Moving time per week" in strava.DYNAMIC_DASHBOARD
    assert "distance-axis" in strava.DYNAMIC_DASHBOARD
    assert "time-axis" in strava.DYNAMIC_DASHBOARD
    assert "drawAxis" in strava.DYNAMIC_DASHBOARD
    assert "niceStep" in strava.DYNAMIC_DASHBOARD
    assert "chart-grid" in strava.DYNAMIC_DASHBOARD
    assert "chart-tooltip" in strava.DYNAMIC_DASHBOARD
    assert "plotHeight=147" in strava.DYNAMIC_DASHBOARD
    assert "height:147px" in strava.DYNAMIC_DASHBOARD
    assert "align-items:center;justify-content:flex-end" in strava.DYNAMIC_DASHBOARD
    assert "scale.values[index]/scale.max*147)+'px'" in strava.DYNAMIC_DASHBOARD
    assert "weekLabel(week.week)" in strava.DYNAMIC_DASHBOARD
    assert "align-items:flex-start" in strava.DYNAMIC_DASHBOARD
    assert "localRoute" in strava.DYNAMIC_DASHBOARD
    assert "Splits" in strava.DYNAMIC_DASHBOARD
    assert "Best efforts" in strava.DYNAMIC_DASHBOARD
    assert "velocity_smooth" in strava.DYNAMIC_DASHBOARD
    assert strava.DYNAMIC_DASHBOARD.index("Recent activity") < strava.DYNAMIC_DASHBOARD.index("Distance per week")
    assert "column-grip" in strava.DYNAMIC_DASHBOARD
    assert "th+th{border-left" in strava.DYNAMIC_DASHBOARD
    assert "td+td,th+th" not in strava.DYNAMIC_DASHBOARD
    assert "text-transform:uppercase" in strava.DYNAMIC_DASHBOARD
    assert "hour'+(hours===1?'':'s')" in strava.DYNAMIC_DASHBOARD
    assert "activity-dialog" in strava.DYNAMIC_DASHBOARD
    assert "/api/activity/" in strava.DYNAMIC_DASHBOARD
    result = run("serve", "--help")
    assert result.returncode == 0 and "--no-sync" in result.stdout

def test_connect_requests_private_activity_scope():
    assert "activity:read,activity:read_all" in strava.connect.__code__.co_consts

if __name__ == "__main__":
    test_status_without_profile(); test_status_json_without_profile_is_machine_readable(); test_profile_units_are_local_configuration(); test_dashboard_uses_local_cache_only(); test_summary_calculates_selected_range(); test_summary_filters_by_specific_strava_sport_type(); test_responsive_dashboard_uses_manual_sync_without_polling(); test_connect_requests_private_activity_scope(); print("ok")
