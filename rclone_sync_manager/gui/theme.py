from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory


def apply_theme(theme: str) -> None:
    app = QApplication.instance()
    if app is None:
        return
    theme = theme.lower()
    app.setStyle(QStyleFactory.create("Fusion"))
    app.setStyleSheet("")
    if theme == "light":
        app.setPalette(_light_palette())
        app.setStyleSheet(_light_stylesheet())
    elif theme == "dark":
        app.setPalette(_dark_palette())
        app.setStyleSheet(_dark_stylesheet())
    else:
        app.setPalette(app.style().standardPalette())


def _light_palette() -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#f6f7f9"))
    palette.setColor(QPalette.WindowText, QColor("#111827"))
    palette.setColor(QPalette.Base, QColor("#ffffff"))
    palette.setColor(QPalette.AlternateBase, QColor("#eef2f7"))
    palette.setColor(QPalette.ToolTipBase, QColor("#ffffff"))
    palette.setColor(QPalette.ToolTipText, QColor("#111827"))
    palette.setColor(QPalette.Text, QColor("#111827"))
    palette.setColor(QPalette.Button, QColor("#e5e7eb"))
    palette.setColor(QPalette.ButtonText, QColor("#111827"))
    palette.setColor(QPalette.BrightText, QColor("#ffffff"))
    palette.setColor(QPalette.Link, QColor("#2563eb"))
    palette.setColor(QPalette.Highlight, QColor("#bfdbfe"))
    palette.setColor(QPalette.HighlightedText, QColor("#111827"))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor("#6b7280"))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor("#6b7280"))
    return palette


def _dark_palette() -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#1f2328"))
    palette.setColor(QPalette.WindowText, QColor("#f3f4f6"))
    palette.setColor(QPalette.Base, QColor("#111418"))
    palette.setColor(QPalette.AlternateBase, QColor("#252a31"))
    palette.setColor(QPalette.ToolTipBase, QColor("#252a31"))
    palette.setColor(QPalette.ToolTipText, QColor("#f3f4f6"))
    palette.setColor(QPalette.Text, QColor("#f3f4f6"))
    palette.setColor(QPalette.Button, QColor("#343a40"))
    palette.setColor(QPalette.ButtonText, QColor("#f3f4f6"))
    palette.setColor(QPalette.BrightText, QColor("#ffffff"))
    palette.setColor(QPalette.Link, QColor("#74c0fc"))
    palette.setColor(QPalette.Highlight, QColor("#3b82f6"))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor("#9ca3af"))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor("#9ca3af"))
    return palette


def _light_stylesheet() -> str:
    return """
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #4b5563;
    border-radius: 2px;
    background: #ffffff;
}
QCheckBox::indicator:hover {
    border: 1px solid #111827;
}
QCheckBox::indicator:checked {
    background: #2563eb;
    border: 1px solid #1d4ed8;
}
QCheckBox::indicator:disabled {
    background: #f3f4f6;
    border: 1px solid #9ca3af;
}
"""


def _dark_stylesheet() -> str:
    return """
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #9ca3af;
    border-radius: 2px;
    background: #111418;
}
QCheckBox::indicator:hover {
    border: 1px solid #f3f4f6;
}
QCheckBox::indicator:checked {
    background: #3b82f6;
    border: 1px solid #74c0fc;
}
QCheckBox::indicator:disabled {
    background: #252a31;
    border: 1px solid #6b7280;
}
"""
