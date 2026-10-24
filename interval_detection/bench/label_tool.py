"""pyqtgraph GUI to annotate structured work intervals in bench activities.

Usage:
    python interval_detection/bench/label_tool.py

Reads ``activities/*.csv`` and writes ``labels/<id>.json``. Each interval is a
draggable shaded region on the power trace with an intensity type.

Controls:
    A           add an interval in the current view
    Delete      remove the interval selected in the list
    Ctrl+S      save
    PageDown    next activity (saves first)
    PageUp      previous activity (saves first)
"""

import sys
from pathlib import Path
from typing import Any, Optional, Sequence

import pyqtgraph as pg
from PyQt6 import QtCore, QtGui, QtWidgets

# Shared with the detector — same denoising for display and detection.
from interval_detection.smoothing import DEFAULT_WINDOW_S, moving_average

sys.path.insert(0, str(Path(__file__).resolve().parent))
import labelio  # noqa: E402


class Labeler(QtWidgets.QMainWindow):
    def __init__(self, activity_ids: Sequence[str]):
        super().__init__()
        self.ids = list(activity_ids)
        self.idx = 0
        self.regions: list[
            Any
        ] = []  # list[pg.LinearRegionItem], each with a .itype attribute
        self._dirty = False  # user edited intervals since load
        self._loaded_labeled = False  # activity already had a labelled state

        self.plot = pg.PlotWidget()
        self.plot.setLabel("bottom", "time", units="s")
        self.plot.setLabel("left", "power", units="W")
        self.curve = self.plot.plot(pen=pg.mkPen((80, 80, 200)))

        self.annot_label = QtWidgets.QLabel("")  # green Annotated / red Not Annotated
        self.meta_label = QtWidgets.QLabel("")
        self.smooth_check = QtWidgets.QCheckBox(f"Smooth ({int(DEFAULT_WINDOW_S)} s)")
        self.smooth_check.toggled.connect(self._redraw_curve)
        self.listw = QtWidgets.QListWidget()
        self.listw.setMaximumWidth(240)
        self.listw.currentRowChanged.connect(self._sync_type_combo)

        self.type_combo = QtWidgets.QComboBox()
        self.type_combo.addItems(labelio.INTERVAL_TYPES)
        self.type_combo.setCurrentText(labelio.DEFAULT_TYPE)
        self.type_combo.setEnabled(False)  # enabled only when an interval is selected
        self.type_combo.currentTextChanged.connect(self._on_type_changed)

        side = QtWidgets.QVBoxLayout()
        side.addWidget(self.annot_label)
        side.addWidget(self.meta_label)
        side.addWidget(self.smooth_check)
        for label, slot in [
            ("Add (A)", self.add_region),
            ("Remove (Del)", self.remove_selected),
            ("Save (Ctrl+S)", self.save),
        ]:
            btn = QtWidgets.QPushButton(label)
            btn.clicked.connect(slot)
            side.addWidget(btn)
        side.addWidget(QtWidgets.QLabel("Intervals:"))
        side.addWidget(self.listw)
        side.addWidget(QtWidgets.QLabel("Selected type:"))
        side.addWidget(self.type_combo)
        nav = QtWidgets.QHBoxLayout()
        for label, slot in [("◀ Prev", self.prev), ("Next ▶", self.next)]:
            btn = QtWidgets.QPushButton(label)
            btn.clicked.connect(slot)
            nav.addWidget(btn)
        side.addLayout(nav)

        central = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(central)
        layout.addWidget(self.plot, 1)
        layout.addLayout(side)
        self.setCentralWidget(central)

        for seq, slot in [
            ("A", self.add_region),
            (QtCore.Qt.Key.Key_Delete, self.remove_selected),
            ("Ctrl+S", self.save),
            (QtCore.Qt.Key.Key_PageDown, self.next),
            (QtCore.Qt.Key.Key_PageUp, self.prev),
        ]:
            QtGui.QShortcut(QtGui.QKeySequence(seq), self).activated.connect(slot)

        self.resize(1100, 600)
        self.load_current()

    @property
    def current_id(self) -> str:
        return self.ids[self.idx]

    def load_current(self) -> None:
        for r in self.regions:
            self.plot.removeItem(r)
        self.regions = []
        self._t, self._p = labelio.load_activity_csv(self.current_id)
        self._redraw_curve()
        self.plot.autoRange()
        ann = labelio.load_annotation(self.current_id)
        self._loaded_labeled = ann["intervals"] is not None
        self._dirty = False
        for s, e, itype in ann["intervals"] or []:
            self._make_region(s, e, itype)
        place = "indoor" if ann["indoor"] else "outdoor"
        self.meta_label.setText(f"{ann['sport_type'] or '?'} · {place}")
        self._update_annot_label()
        self.refresh_list()

    def _update_annot_label(self) -> None:
        if self._loaded_labeled:
            self.annot_label.setText("Annotated")
            self.annot_label.setStyleSheet(
                "color: green; font-weight: bold; font-size: 14pt;"
            )
        else:
            self.annot_label.setText("Not Annotated")
            self.annot_label.setStyleSheet(
                "color: red; font-weight: bold; font-size: 14pt;"
            )

    def _redraw_curve(self) -> None:
        # Redraws the power trace only — leaves interval regions untouched.
        p = (
            moving_average(self._t, self._p)
            if self.smooth_check.isChecked()
            else self._p
        )
        self.curve.setData(self._t, p)

    def _make_region(
        self, start: float, end: float, itype: str = labelio.DEFAULT_TYPE
    ) -> Any:
        region = pg.LinearRegionItem([start, end], brush=pg.mkBrush(255, 140, 0, 60))
        region.itype = itype
        region.sigRegionChangeFinished.connect(self._on_region_changed)
        self.plot.addItem(region)
        self.regions.append(region)
        return region

    def _on_region_changed(self) -> None:
        self._dirty = True
        self.refresh_list()

    def add_region(self) -> None:
        (x0, x1), _ = self.plot.getViewBox().viewRange()
        centre = 0.5 * (x0 + x1)
        half = min(30.0, 0.1 * (x1 - x0))
        region = self._make_region(centre - half, centre + half)
        self._dirty = True
        self.refresh_list()
        self._select_region(region)  # so the type combo immediately controls it

    def _sorted_regions(self) -> list:
        return sorted(self.regions, key=lambda r: r.getRegion()[0])

    def intervals(self) -> list:
        return [(*r.getRegion(), r.itype) for r in self._sorted_regions()]

    def _selected_region(self) -> Optional[Any]:
        row = self.listw.currentRow()
        ordered = self._sorted_regions()
        return ordered[row] if 0 <= row < len(ordered) else None

    def _select_region(self, region: Any) -> None:
        ordered = self._sorted_regions()
        if region in ordered:
            self.listw.setCurrentRow(ordered.index(region))

    def remove_selected(self) -> None:
        region = self._selected_region()
        if region is not None:
            self.regions.remove(region)
            self.plot.removeItem(region)
            self._dirty = True
            self.refresh_list()

    def _sync_type_combo(self) -> None:
        region = self._selected_region()
        self.type_combo.setEnabled(region is not None)
        if region is not None:
            self.type_combo.blockSignals(True)
            self.type_combo.setCurrentText(region.itype)
            self.type_combo.blockSignals(False)

    def _on_type_changed(self, itype: str) -> None:
        region = self._selected_region()
        if region is not None and region.itype != itype:
            region.itype = itype
            self._dirty = True
            self.refresh_list()

    def refresh_list(self) -> None:
        row = self.listw.currentRow()
        self.listw.blockSignals(True)
        self.listw.clear()
        for s, e, itype in self.intervals():
            self.listw.addItem(f"{s:6.0f}–{e:6.0f}s ({e - s:.0f}s) [{itype}]")
        if 0 <= row < self.listw.count():
            self.listw.setCurrentRow(row)
        self.listw.blockSignals(False)
        self._sync_type_combo()
        self.setWindowTitle(
            f"[{self.idx + 1}/{len(self.ids)}] {self.current_id} "
            f"— {len(self.regions)} intervals"
        )

    def save(self) -> None:
        # An explicit save always marks the activity annotated, even with 0 intervals.
        path = labelio.save_intervals(self.current_id, self.intervals())
        self._dirty = False
        self._loaded_labeled = True
        self._update_annot_label()
        if bar := self.statusBar():
            bar.showMessage(f"saved {path}", 3000)

    def _autosave(self) -> None:
        # Don't mark a merely-viewed, never-labelled activity as annotated.
        if self._dirty or self._loaded_labeled:
            self.save()

    def next(self) -> None:
        self._autosave()
        self.idx = (self.idx + 1) % len(self.ids)
        self.load_current()

    def prev(self) -> None:
        self._autosave()
        self.idx = (self.idx - 1) % len(self.ids)
        self.load_current()


def main() -> int:
    ids = labelio.list_activity_ids()
    if not ids:
        print(
            f"No activities in {labelio.ACTIVITIES_DIR}.\n"
            f"Export some first, e.g.:  python -m scripts.export_for_bench <activity_id>"
        )
        return 1
    app = QtWidgets.QApplication(sys.argv)
    window = Labeler(ids)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
