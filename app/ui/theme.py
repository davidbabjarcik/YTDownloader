from __future__ import annotations
from string import Template

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication

DARK = dict(bg="#14161b", panel="#1b1e25", card="#242833", border="#2f3441", text="#e8eaf0",
            muted="#8d95a8", accent="#7c5cff", accent2="#9277ff", danger="#ff5c6c",
            ok="#3ddc97", input="#1a1d24", err_bg="rgba(255,92,108,0.12)")
LIGHT = dict(bg="#f3f4f8", panel="#ffffff", card="#ffffff", border="#d6dae5", text="#1c2030",
             muted="#697186", accent="#6a4cff", accent2="#7f64ff", danger="#d93a4c",
             ok="#1fae73", input="#ffffff", err_bg="rgba(217,58,76,0.10)")

QSS = Template("""
QWidget { background:$bg; color:$text; font-family:"Segoe UI","Inter",sans-serif; font-size:10pt; }
QLabel { background:transparent; }
QLabel#muted { color:$muted; }
QLabel#h1 { font-size:18pt; font-weight:700; }
QLabel#h2 { font-size:13pt; font-weight:600; }
QLabel#ok { color:$ok; font-weight:600; }
QFrame#sidebar { background:$panel; border-right:1px solid $border; }
QFrame#card, QFrame#queueItem { background:$card; border:1px solid $border; border-radius:12px; }
QFrame#card QLabel, QFrame#queueItem QLabel { background:transparent; }
QFrame#banner { background:$card; border:1px solid $accent; border-radius:10px; }
QFrame#errorBox { background:$err_bg; border:1px solid $danger; border-radius:10px; }
QFrame#okBox { background:$card; border:1px solid $ok; border-radius:10px; }
QPushButton { background:$card; border:1px solid $border; border-radius:8px; padding:7px 14px; }
QPushButton:hover { border-color:$accent; }
QPushButton:disabled { color:$muted; }
QPushButton#primary { background:$accent; color:white; border:none; font-weight:700; padding:10px 24px; }
QPushButton#primary:hover { background:$accent2; }
QPushButton#primary:disabled { background:$border; color:$muted; }
QPushButton#nav { text-align:left; border:none; background:transparent; padding:11px 16px; border-radius:8px; }
QPushButton#nav:hover { background:$card; }
QPushButton#nav:checked { background:$card; color:$accent2; font-weight:600; }
QLineEdit, QPlainTextEdit, QComboBox, QSpinBox { background:$input; border:1px solid $border;
  border-radius:8px; padding:6px 9px; selection-background-color:$accent; }
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border-color:$accent; }
QPlainTextEdit#url { font-size:11pt; padding:10px; }
QComboBox QAbstractItemView { background:$panel; selection-background-color:$accent; border:1px solid $border; }
QProgressBar { background:$input; border:none; border-radius:6px; text-align:center; min-height:14px; max-height:14px; }
QProgressBar::chunk { background:$accent; border-radius:6px; }
QListWidget { background:$panel; border:1px solid $border; border-radius:10px; outline:0; }
QListWidget::item { padding:4px; border-bottom:1px solid $border; }
QListWidget::item:selected { background:$card; color:$text; }
QGroupBox { border:1px solid $border; border-radius:10px; margin-top:16px; padding:16px 12px 10px 12px; }
QGroupBox::title { subcontrol-origin:margin; left:12px; padding:0 6px; color:$muted; }
QScrollArea { border:none; }
QScrollBar:vertical { background:transparent; width:10px; }
QScrollBar::handle:vertical { background:$border; border-radius:5px; min-height:30px; }
QScrollBar::add-line, QScrollBar::sub-line { height:0; }
QToolTip { background:$card; color:$text; border:1px solid $border; }
""")


def resolve(name: str) -> str:
    if name == "system":
        try:
            dark = QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
        except Exception:  # noqa: BLE001
            dark = True
        return "dark" if dark else "light"
    return name if name in ("dark", "light") else "dark"


def apply_theme(app, name: str) -> str:
    resolved = resolve(name)
    app.setStyleSheet(QSS.substitute(DARK if resolved == "dark" else LIGHT))
    try:  # Qt 6.8+: also colours the native title bar on Windows
        hints = app.styleHints()
        hints.setColorScheme({"dark": Qt.ColorScheme.Dark, "light": Qt.ColorScheme.Light}
                             .get(name, Qt.ColorScheme.Unknown))
    except Exception:  # noqa: BLE001
        pass
    return resolved
