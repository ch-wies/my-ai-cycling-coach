# bench

Test bench for the interval detector.

- `activities/` — activities in the neutral CSV format (`t,power`), one file per
  activity (`<activity_id>.csv`). Produced by the app-side export script
  (`scripts/export_for_bench.py` in the fit-data-viewer app while co-located).
- `labels/` — ground-truth interval labels, one JSON per activity
  (`<activity_id>.json`), each a list of `[start_s, end_s]` pairs.
- `labelio.py` — pure (no-GUI) load/save helpers for activities and labels.
- `label_tool.py` — pyqtgraph GUI for annotating intervals. Run:
  `python interval_detection/bench/label_tool.py`
  (A = add · Delete = remove selected · Ctrl+S = save · PageUp/PageDown = prev/next activity).
- `evaluate.py` — (TODO) IoU@0.5 matching → precision/recall/F1 + boundary error.

Activities and labels are committed to git in this stripped form.
