# My AI Cycling Coach

A desktop application for analyzing cycling performance data from intervals.icu activities, with an AI-powered training coach.

## Features

- **Sync from intervals.icu**: Load the past year of activities directly from intervals.icu metadata
- **Interactive Plotting**: Visualize power output and heart rate with synchronized charts
- **Time Selection**: Click-drag to select time ranges and analyze specific intervals
- **Performance Analytics**: Calculate statistics (mean, max, min, std dev) for selected intervals
- **AI Training Coach**: Generate personalized training plans, adapt them based on completed workouts, and chat with an AI coach about your progress

## Tech Stack

- **Linux System**: Should in theory work on other platforms as well but might need some adaption
- **Python 3.9+**
- **PyQt6**: Desktop application framework
- **PyQtGraph**: High-performance data visualization
- **pandas/NumPy**: Data processing
- **Anthropic Claude**: AI training coach (claude-sonnet-5-5)

## Installation

From the project directory, run the setup script:

```bash
./setup.sh
```

This creates a virtual environment, installs dependencies, and registers the app as a desktop entry (icon + launcher).

For development (adds `pytest`, `ruff`, `mypy`, etc.), pass `--dev`:

```bash
./setup.sh --dev
```

## Authentication

### intervals.icu

Authentication is a static personal API key — no OAuth flow required.

1. Sign in at [intervals.icu](https://intervals.icu) and go to **Settings → Developer Settings**.
2. Copy your **API Key**. Your **athlete ID** (e.g. `i123456`) is shown on the same page and in your profile URL.
3. Create `~/.my-ai-cycling-coach/intervals_config.json`:

```bash
mkdir -p ~/.my-ai-cycling-coach
cat > ~/.my-ai-cycling-coach/intervals_config.json <<'EOF'
{
  "athlete_id": "i123456",
  "api_key": "your-api-key-here"
}
EOF
chmod 600 ~/.my-ai-cycling-coach/intervals_config.json
```

Keep this file private — it contains sensitive credentials.

> **Note:** the app previously synced from Strava. That integration was removed from the codebase after Strava moved API access behind a paid subscription — it's preserved in git history if ever needed again.

### Claude API (AI Training Features)

The Training tab uses the Claude API from Anthropic for AI-powered plan generation, adaptation, and coaching chat. This requires a **separate API account** — a Claude.ai subscription does not grant API access.

#### Setting up your Claude API key

1. Sign up at [console.anthropic.com](https://console.anthropic.com)
2. Add a payment method. Usage is billed per token — generating or adapting a training plan typically costs a few cents per run; chat is similarly inexpensive.
3. Navigate to **API Keys** and create a new key.
4. Save the key to `~/.my-ai-cycling-coach/claude_api_key`:

```bash
mkdir -p ~/.my-ai-cycling-coach
echo "sk-ant-your-key-here" > ~/.my-ai-cycling-coach/claude_api_key
chmod 600 ~/.my-ai-cycling-coach/claude_api_key
```

> **Keep your API key private.** Anyone with your key can make API calls billed to your account.

## Usage

### Running the Application

```bash
python main.py
```

### Test Mode

Pass `--test` to point the app at an isolated data directory
(`~/.my-ai-cycling-coach-test` instead of `~/.my-ai-cycling-coach`) — useful
for trying out changes without touching your real config, plans, or goals:

```bash
python main.py --test
```

### Loading Activities

On startup, activities from the last year are loaded from intervals.icu using metadata only.

1. Use the **Refresh Activities** button to re-sync the latest activity list from intervals.icu.
2. Select an activity in the table to download its full data and display it.

### Analyzing Data

1. Select primary and secondary metrics from the dropdowns.
2. Click and drag on the plot to select a time range.
3. View statistics for the selected interval in the **Selection Statistics** panel.
4. Use middle mouse button to pan, scroll wheel to zoom.

### AI Training Coach

Navigate to the **Training** tab to use the AI features:

1. **Generate Plan**: Fill in your training goals (target event, weekly hours, current FTP, etc.) and click **Generate Plan**. The plan is saved to `~/.my-ai-cycling-coach/plan_original.md` and displayed in the viewer.
2. **Adapt Plan**: After completing some workouts, click **Adapt Plan**. The AI queries your recent intervals.icu activities, compares them against the plan, and writes an updated version to `~/.my-ai-cycling-coach/plan_adapted.md`.
3. **Chat**: Use the chat panel at the bottom to ask your AI coach questions about your progress, request session advice, or discuss adjustments to the plan.

## Development

### Running checks

```bash
./check.sh
```

Runs `ruff check`, `ruff format --check`, `mypy`, and `pytest`, and exits non-zero if any of them fail.

### Managing dependencies

Dependencies are pinned with [pip-tools](https://github.com/jazzband/pip-tools) so releases are reproducible:

- `requirements.in` / `requirements-dev.in` are the source of truth — the direct dependencies the project actually needs, without version pins.
- `requirements.txt` / `requirements-dev.txt` are generated lock files with every dependency (direct and transitive) pinned to an exact version. These are what `setup.sh` installs from — never edit them by hand.

To add or change a dependency, edit the relevant `.in` file, then regenerate the lock files:

```bash
source venv/bin/activate
pip-compile --allow-unsafe --no-strip-extras requirements.in -o requirements.txt
pip-compile --allow-unsafe --no-strip-extras requirements-dev.in -o requirements-dev.txt
```

To upgrade pinned versions (e.g. before cutting a release), add `--upgrade` to either command above.

After regenerating, sync your venv to match the lock file exactly (installs additions, removes anything no longer required):

```bash
pip-sync requirements-dev.txt
```

Run `./check.sh` afterwards to confirm the project still works with the new versions before committing the updated lock files.

## License

MIT License
