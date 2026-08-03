from __future__ import annotations

import re

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from src.core.compound_profiles import get_color, get_effects
from src.models.result import ParsedResult


def _strip_name(name: str) -> str:
    idx = name.find(" - ")
    if idx > 0:
        return name[idx + 3:]
    return name


class _BarChart(QWidget):
    """Horizontal bar chart with one row per compound.

    Colors come from the single source of truth (data/cannabinoids_terpenes.txt)
    via src.core.compound_profiles; effects are shown as a subtitle under each
    name and in the row tooltip.
    """

    _MARGIN = 12
    _ROW_GAP = 4

    def __init__(self, title: str, items: list[tuple[str, float, str | None, str, float | None, str | None]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._title = title
        self._max_val = max((v for _, v, _, _, _, _ in items), default=0.0)
        self._rows = [self._make_row(*item) for item in items]

        self._name_font = QFont()
        self._name_font.setPixelSize(11)
        self._value_font = QFont(self._name_font)
        self._value_font.setBold(True)
        self._sub_font = QFont(self._name_font)
        self._sub_font.setPixelSize(9)
        self._title_font = QFont()
        self._title_font.setPixelSize(12)
        self._title_font.setBold(True)

        self._left_col = self._measure_left_col()
        self._right_col = max(
            (QFontMetricsF(self._value_font).horizontalAdvance(row["value_text"])
             for row in self._rows),
            default=0.0,
        ) + 8.0
        self._row_height = max(
            (QFontMetricsF(self._name_font).height()
             + (QFontMetricsF(self._sub_font).height() if (row["effects_text"] or row["sub_text"]) else 0)
             for row in self._rows),
            default=18.0,
        ) + 6.0

        self.setMinimumHeight(int(self._content_height()))
        self.setMouseTracking(True)
        self._hover_row: int | None = None

    def _make_row(self, name: str, value: float, val_unit: str | None, kind: str, mg: float | None, unit: str | None) -> dict:
        is_total = name.lower().startswith("total ")
        color = get_color(name) or _get_color(name, kind == "terpene")
        if is_total:
            color = "#37474F"
        effects = get_effects(name)

        if val_unit:
            value_text = f"{value:.3f} {val_unit}"
        else:
            value_text = f"{value:.3f}%"
        sub_text = f"{mg:.3f} {unit}" if mg is not None else ""

        return {
            "name": name,
            "value": value,
            "kind": kind,
            "mg": mg,
            "unit": unit or "",
            "val_unit": val_unit,
            "color": color,
            "is_total": is_total,
            "effects_text": ", ".join(effects),
            "value_text": value_text,
            "sub_text": sub_text,
        }

    def _measure_left_col(self) -> float:
        metrics = QFontMetricsF(self._name_font)
        widths = [metrics.horizontalAdvance(row["name"]) for row in self._rows]
        return (max(widths) if widths else 60.0) + 12.0

    def _content_height(self) -> float:
        return 26 + 8 + sum(self._row_height + self._ROW_GAP for _ in self._rows) + 4

    def sizeHint(self) -> QSize:
        return QSize(520, int(self._content_height()))

    def _bar_rect(self, width: float, top: float) -> QRectF:
        x0 = self._MARGIN + self._left_col
        x1 = width - self._MARGIN - self._right_col
        return QRectF(x0, top, max(1.0, x1 - x0), self._row_height)

    def paintEvent(self, event: "object") -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        painter.setFont(self._title_font)
        painter.setPen(QColor("#222"))
        painter.drawText(QRectF(self._MARGIN, 6, self.width() - 2 * self._MARGIN, 20), Qt.AlignLeft | Qt.AlignVCenter, self._title)

        y = 26 + 8
        bar_area = self._bar_rect(self.width(), y)

        if not self._rows:
            painter.setFont(self._name_font)
            painter.setPen(QColor("#888"))
            painter.drawText(QRectF(bar_area.left(), y, bar_area.width(), 20), Qt.AlignLeft | Qt.AlignVCenter, "No compounds detected.")
            return

        # gridlines
        if self._max_val > 0:
            grid_pen = QPen(QColor("#e2e2e2"))
            grid_pen.setWidthF(1.0)
            painter.setPen(grid_pen)
            for frac in (0.25, 0.5, 0.75, 1.0):
                gx = bar_area.left() + bar_area.width() * frac
                painter.drawLine(QPointF(gx, bar_area.top() - 2), QPointF(gx, bar_area.bottom() + 2))

        baseline = QPen(QColor("#b0b0b0"))
        baseline.setWidthF(1.0)
        painter.setPen(baseline)
        painter.drawLine(QPointF(bar_area.left(), bar_area.top() - 2), QPointF(bar_area.left(), bar_area.bottom() + 2))

        row_idx = 0
        for row in self._rows:
            top = y + self._row_height * row_idx + self._ROW_GAP * row_idx
            name_metrics = QFontMetricsF(self._name_font)
            sub_metrics = QFontMetricsF(self._sub_font)

            painter.setFont(self._name_font)
            painter.setPen(QColor("#222"))
            painter.drawText(QRectF(self._MARGIN, top, self._left_col, name_metrics.height()),
                             Qt.AlignLeft | Qt.AlignVCenter, row["name"])

            bar_rect = self._bar_rect(self.width(), top)
            bar_height = self._row_height - 4.0
            bar_rect.setTop(bar_rect.top() + 2.0)
            bar_rect.setHeight(bar_height)

            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#efefef"))
            painter.drawRoundedRect(bar_rect, 3.0, 3.0)

            if self._max_val > 0 and row["value"] > 0:
                fill_width = bar_rect.width() * (row["value"] / self._max_val)
                fill = QRectF(bar_rect.left(), bar_rect.top(), max(2.0, fill_width), bar_rect.height())
                base_color = QColor(row["color"])
                gradient = QLinearGradient(fill.topLeft(), fill.topRight())
                gradient.setColorAt(0.0, base_color.lighter(112))
                gradient.setColorAt(1.0, base_color)
                painter.setBrush(gradient)
                painter.drawRoundedRect(fill, 3.0, 3.0)
                if row["is_total"]:
                    pen = QPen(base_color.darker(135))
                    pen.setWidthF(1.2)
                    painter.setPen(pen)
                    painter.drawRoundedRect(fill, 3.0, 3.0)

            sub = ""
            if row["effects_text"]:
                sub = row["effects_text"]
            elif row["sub_text"]:
                sub = row["sub_text"]

            if sub:
                painter.setFont(self._sub_font)
                painter.setPen(QColor("#8a8a8a"))
                if row["effects_text"]:
                    max_effects_w = bar_rect.right() - self._MARGIN
                    sub = QFontMetricsF(self._sub_font).elidedText(row["effects_text"], Qt.ElideRight, int(max_effects_w))
                painter.drawText(QRectF(self._MARGIN, top + name_metrics.height(), self._left_col, sub_metrics.height()),
                                 Qt.AlignLeft | Qt.AlignVCenter, sub)

            painter.setFont(self._value_font)
            painter.setPen(QColor("#333"))
            value_rect = QRectF(self.width() - self._MARGIN - self._right_col, top, self._right_col, name_metrics.height())
            painter.drawText(value_rect, Qt.AlignRight | Qt.AlignVCenter, row["value_text"])

            if row["sub_text"] and row["effects_text"]:
                painter.setFont(self._sub_font)
                painter.setPen(QColor("#8a8a8a"))
                painter.drawText(QRectF(self.width() - self._MARGIN - self._right_col, top + name_metrics.height(),
                                        self._right_col, sub_metrics.height()),
                                 Qt.AlignRight | Qt.AlignVCenter, row["sub_text"])

            row_idx += 1

        painter.end()

    def _row_at(self, y: float) -> int | None:
        if not self._rows:
            return None
        start = 26 + 8
        for idx in range(len(self._rows)):
            row_top = start + idx * (self._row_height + self._ROW_GAP)
            if row_top <= y <= row_top + self._row_height:
                return idx
        return None

    def mouseMoveEvent(self, event: "object") -> None:
        idx = self._row_at(event.position().y())
        if idx != self._hover_row:
            self._hover_row = idx
            if idx is not None:
                row = self._rows[idx]
                lines = [row["name"], row["value_text"]]
                if row["sub_text"]:
                    lines.append(row["sub_text"])
                if row["effects_text"]:
                    lines.append(row["effects_text"])
                self.setToolTip("\n".join(lines))
            else:
                self.setToolTip("")
        super().mouseMoveEvent(event)


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
        self._cannabinoid_section: _BarChart | None = None
        self._terpene_section: _BarChart | None = None

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
        self._cannabinoid_section = _BarChart("CANNABINOIDS", blend_canna)
        self._layout.addWidget(self._cannabinoid_section)
        self._terpene_section = _BarChart("TERPENES", blend_terps)
        self._layout.addWidget(self._terpene_section)

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
                self._layout.addWidget(_BarChart(f"{strain_name} \u2014 Cannabinoids", s_canna))
            if s_terps:
                self._layout.addWidget(_BarChart(f"{strain_name} \u2014 Terpenes", s_terps))

        self._layout.addStretch()
