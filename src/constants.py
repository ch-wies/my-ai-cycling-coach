"""Application-wide constants — single source of truth for names, paths, and settings"""

import sys
from pathlib import Path

APP_NAME = "My AI Cycling Coach"
_test_mode = "--test" in sys.argv
APP_DIR = Path.home() / (
    ".my-ai-cycling-coach-test" if _test_mode else ".my-ai-cycling-coach"
)

# Persisted file paths
INTERVALS_CONFIG_PATH = APP_DIR / "intervals_config.json"
CLAUDE_API_KEY_PATH = APP_DIR / "claude_api_key"
PLAN_ORIGINAL_PATH = APP_DIR / "plan_original.md"
PLAN_ADAPTED_PATH = APP_DIR / "plan_adapted.md"
SESSIONS_ORIGINAL_PATH = APP_DIR / "sessions_original.csv"
SESSIONS_ADAPTED_PATH = APP_DIR / "sessions_adapted.csv"
SESSIONS_LOG_PATH = APP_DIR / "sessions_log.json"
GOALS_PATH = APP_DIR / "goals.json"
LOG_PATH = APP_DIR / "app.log"

# AI settings
AI_MODEL = "claude-sonnet-5-5"

# Activity history window used by the plan adaptor agent and coach chat
ACTIVITY_HISTORY_WEEKS = 8
