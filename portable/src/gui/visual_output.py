from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.models.result import ParsedResult


def _strip_name(name: str) -> str:
    idx = name.find(" - ")
    if idx > 0:
        return name[idx + 3:]
    return name


class _BarRow(QWidget):
    def __init__(self, name: str, value: float, pct_of_max: float, color: str, bold: bool = False, mg: float | None = None, unit: str = "", val_unit: str | None = None) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        name_label = QLabel(name)
        name_label.setMinimumWidth(90)
        name_label.setStyleSheet(f"font-size: 11px; font-weight: {'600' if bold else '400'};")
        layout.addWidget(name_label)

        track = QFrame()
        track.setFixedHeight(12)
        track.setStyleSheet("background-color: transparent;")
        track_layout = QHBoxLayout(track)
        track_layout.setContentsMargins(0, 0, 0, 0)
        track_layout.setSpacing(0)

        bar = QFrame()
        bar.setFixedHeight(12)
        bar.setStyleSheet(f"""
            background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {color}, stop:1 {color});
            border-radius: 3px;
        """)
        track_layout.addWidget(bar)

        if pct_of_max < 1.0:
            filler = QWidget()
            filler.setStyleSheet("background-color: transparent;")
            track_layout.addWidget(filler)
            bar_stretch = max(1, int(pct_of_max * 700))
            filler_stretch = max(300, 1000 - bar_stretch)
            track_layout.setStretchFactor(bar, bar_stretch)
            track_layout.setStretchFactor(filler, filler_stretch)

        layout.addWidget(track, stretch=1)

        if val_unit:
            if mg is not None:
                val_label = QLabel(f"{value:.3f} {val_unit}  ({mg:.3f} {unit})")
            else:
                val_label = QLabel(f"{value:.3f} {val_unit}")
        elif mg is not None:
            val_label = QLabel(f"{value:.3f}%  ({mg:.3f} {unit})")
        else:
            val_label = QLabel(f"{value:.3f}%")
        val_label.setStyleSheet("font-size: 11px;")
        val_label.setMinimumWidth(70)
        val_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(val_label)


class _Section(QWidget):
    def __init__(self, title: str, items: list[tuple[str, float, str | None, str, float | None, str | None]], total_name: str | None = None) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QLabel(title)
        header.setStyleSheet("font-size: 12px; font-weight: 700; margin-top: 6px; margin-bottom: 2px;")
        layout.addWidget(header)

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("background-color: #ccc; max-height: 1px;")
        layout.addWidget(separator)

        if not items:
            empty = QLabel("No compounds detected.")
            empty.setStyleSheet("font-size: 12px; color: #888; margin: 8px 0;")
            layout.addWidget(empty)
            return

        max_val = max(v for _, v, _, _, _, _ in items)
        for name, val, val_unit, compound_type, mg, unit in items:
            is_total = name.lower().startswith("total ")
            is_terp = compound_type == "terpene"
            color = _get_color(name, is_terp)
            bar = _BarRow(name, val, val / max_val if max_val > 0 else 0, color, bold=is_total, mg=mg, unit=unit or "", val_unit=val_unit)
            layout.addWidget(bar)


_CANNABIS_COLORS = [
    "#4CAF50", "#66BB6A", "#81C784", "#A5D6A7",
    "#2196F3", "#42A5F5", "#64B5F6",
    "#FF9800", "#FFA726", "#FFB74D",
    "#AB47BC", "#CE93D8",
    "#78909C", "#90A4AE",
]

_TERPENE_COLORS = [
    "#8D6E63", "#A1887F", "#BCAAA4",
    "#26A69A", "#4DB6AC", "#80CBC4",
    "#EC407A", "#F06292", "#F48FB1",
    "#7E57C2", "#9575CD", "#B39DDB",
    "#5C6BC0", "#7986CB", "#9FA8DA",
]

_CANNABINOID_KEYWORDS = {
    "thc": "#2E7D32",
    "thca": "#388E3C",
    "thcv": "#43A047",
    "delta-9-thc": "#1B5E20",
    "delta-8-thc": "#4CAF50",
    "cbd": "#1565C0",
    "cbda": "#1976D2",
    "cbdv": "#1E88E5",
    "cbn": "#E65100",
    "cbg": "#F57C00",
    "cbga": "#FB8C00",
    "cbc": "#7B1FA2",
    "cbl": "#8E24AA",
    "total": "#37474F",
}

_TERPENE_KEYWORDS: dict[str, str] = {}


def _get_color(name: str, is_terpene: bool) -> str:
    key = name.lower().replace(" ", "-").replace("_", "-")
    if is_terpene:
        idx = hash(key) % len(_TERPENE_COLORS)
        return _TERPENE_COLORS[idx]
    for kw, color in _CANNABINOID_KEYWORDS.items():
        if kw in key:
            return color
    idx = hash(key) % len(_CANNABIS_COLORS)
    return _CANNABIS_COLORS[idx]


def _parse_items(text: str) -> list[tuple[str, float, str | None, str, float | None, str | None]]:
    result = []
    MB_PCT = re.compile(r"^\s*(.+?)\s*:\s*([\d.]+)%\s*(?:\(([\d.]+)\s*(mg/g|mg/unit)\))?\s*$")
    MB_EDIBLE = re.compile(r"^\s*(.+?)\s*:\s*([\d.]+)\s+(mg/unit|mg/g)(?:\s*\(([\d.]+)\s*mg/g\))?\s*$")
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        m = MB_PCT.match(line)
        if m:
            name = m.group(1).strip()
            val = float(m.group(2))
            mg = float(m.group(3)) if m.group(3) else None
            unit = m.group(4)
            val_unit = None
        else:
            m = MB_EDIBLE.match(line)
            if not m:
                continue
            name = m.group(1).strip()
            val = float(m.group(2))
            val_unit = m.group(3)
            mg = float(m.group(4)) if m.group(4) else None
            unit = "mg/g" if mg is not None else None
        stripped = _strip_name(name).lower()
        stripped = re.sub(r'\ba-(?=[A-Za-z])', 'alpha-', stripped)
        stripped = re.sub(r'\bb-(?=[A-Za-z])', 'beta-', stripped)
        stripped = re.sub(r'\by-(?=[A-Za-z])', 'gamma-', stripped)
        is_terp = stripped in {
            "myrcene", "limonene", "pinene", "linalool", "caryophyllene",
            "humulene", "terpinolene", "ocimene", "bisabolol", "nerolidol",
            "guaiol", "valencene", "geraniol", "camphene", "borneol",
            "eucalyptol", "terpineol", "fenchol", "sabinene", "phellandrene",
            "3-carene", "pulegone", "geranyl acetate", "citronellol", "nerol",
            "isopulegol", "beta-myrcene", "alpha-pinene", "beta-pinene",
            "beta-caryophyllene", "alpha-humulene", "trans-nerolidol",
            "alpha-bisabolol", "beta-ocimene", "d-limonene", "caryophyllene oxide",
            "alpha-terpinene", "gamma-terpinene", "p-cymene", "alpha-terpineol",
            "cis-ocimene", "trans-ocimene", "total terpenes",
            "farnesene", "trans-beta-farnesene", "trans-beta-farnesol",
        }
        compound_type = "terpene" if is_terp else "cannabinoid"
        result.append((name, val, val_unit, compound_type, mg, unit))
    return result


class VisualOutputWidget(QScrollArea):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self._content = QWidget()
        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(16, 8, 16, 8)
        self._layout.setSpacing(0)
        self.setWidget(self._content)

        self._info_grid: QWidget | None = None
        self._cannabinoid_section: _Section | None = None
        self._terpene_section: _Section | None = None

    def display(self, result: ParsedResult, raw_text: str) -> None:
        old = self.takeWidget()
        if old is not None:
            old.setParent(None)
            old.deleteLater()

        self._content = QWidget()
        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(16, 8, 16, 8)
        self._layout.setSpacing(0)
        self.setWidget(self._content)

        meta = result.metadata

        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        info_layout.setContentsMargins(0, 0, 0, 8)
        info_layout.setSpacing(2)

        fields = [
            ("Product", meta.get("product_name") or "-"),
            ("Company", meta.get("company_name") or "-"),
            ("Lab", result.format_name or "-"),
            ("Date", meta.get("report_date") or "-"),
            ("Category", meta.get("metrc_category") or "-"),
        ]
        for label_text, value in fields:
            row = QHBoxLayout()
            row.setSpacing(8)
            lbl = QLabel(f"{label_text}:")
            lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #555;")
            lbl.setFixedWidth(70)
            val = QLabel(value)
            val.setStyleSheet("font-size: 12px;")
            row.addWidget(lbl)
            row.addWidget(val)
            row.addStretch()
            info_layout.addLayout(row)

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("background-color: #ccc; max-height: 1px;")
        info_layout.addWidget(separator)

        self._layout.addWidget(info_widget)

        def sort_key(item: tuple) -> tuple:
            n, v, _, _, _, _ = item
            is_total = n.lower().startswith("total ")
            return (0 if is_total else 1, -v)

        def parse_items_to_tuples(raw: list[str]) -> list[tuple[str, float, str | None, str, float | None, str | None]]:
            text = "\n".join(raw)
            return _parse_items(text)

        # Section 1: blend — from result.items (raw text-extracted items)
        blend_parsed = parse_items_to_tuples(result.items)
        blend_canna = [(n, v, vu, t, mg, u) for n, v, vu, t, mg, u in blend_parsed if t != "terpene"]
        blend_terps = [(n, v, vu, t, mg, u) for n, v, vu, t, mg, u in blend_parsed if t == "terpene"]
        blend_canna.sort(key=sort_key)
        blend_terps.sort(key=sort_key)
        self._layout.addWidget(_Section("CANNABINOIDS", blend_canna))
        self._layout.addWidget(_Section("TERPENES", blend_terps))

        # Sections 2, 3, ...: individual strains from OCR
        strain_groups = result.metadata.get("strain_groups", [])
        for strain_name, strain_items in strain_groups:
            sep = QFrame()
            sep.setFrameShape(QFrame.HLine)
            sep.setStyleSheet("background-color: #bbb; max-height: 2px; margin: 12px 0;")
            self._layout.addWidget(sep)

            strain_parsed = parse_items_to_tuples(strain_items)
            s_canna = [(n, v, vu, t, mg, u) for n, v, vu, t, mg, u in strain_parsed if t != "terpene"]
            s_terps = [(n, v, vu, t, mg, u) for n, v, vu, t, mg, u in strain_parsed if t == "terpene"]
            s_canna.sort(key=sort_key)
            s_terps.sort(key=sort_key)

            if s_canna:
                self._layout.addWidget(_Section(f"{strain_name} \u2014 Cannabinoids", s_canna))
            if s_terps:
                self._layout.addWidget(_Section(f"{strain_name} \u2014 Terpenes", s_terps))

        self._layout.addStretch()
