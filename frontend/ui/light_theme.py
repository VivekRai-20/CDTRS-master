"""
CDTRS always uses its light theme.

When Windows is set to dark mode, Qt gives every widget a dark default
palette.  The stylesheet colours the main surfaces, but list areas, scroll
areas and panels that only use the default colours turned black.  A fixed
light palette keeps the whole application light, whatever the Windows
setting.
"""

from PySide6.QtGui import QColor, QPalette

PAGE_BG = "#F5F7FA"
TEXT = "#1F2937"
MUTED = "#64748B"


def apply_light_theme(app) -> None:
    palette = QPalette()
    colours = {
        QPalette.ColorRole.Window: PAGE_BG,
        QPalette.ColorRole.WindowText: TEXT,
        QPalette.ColorRole.Base: "#FFFFFF",
        QPalette.ColorRole.AlternateBase: "#F8FAFC",
        QPalette.ColorRole.Text: TEXT,
        QPalette.ColorRole.Button: "#F1F5F9",
        QPalette.ColorRole.ButtonText: TEXT,
        QPalette.ColorRole.BrightText: "#FFFFFF",
        QPalette.ColorRole.Highlight: "#2563EB",
        QPalette.ColorRole.HighlightedText: "#FFFFFF",
        QPalette.ColorRole.ToolTipBase: "#0F172A",
        QPalette.ColorRole.ToolTipText: "#FFFFFF",
        QPalette.ColorRole.PlaceholderText: "#94A3B8",
        QPalette.ColorRole.Link: "#2563EB",
        QPalette.ColorRole.Light: "#FFFFFF",
        QPalette.ColorRole.Midlight: "#E2E8F0",
        QPalette.ColorRole.Mid: "#CBD5E1",
        QPalette.ColorRole.Dark: "#94A3B8",
        QPalette.ColorRole.Shadow: "#475569",
    }
    for role, colour in colours.items():
        palette.setColor(QPalette.ColorGroup.All, role, QColor(colour))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor("#94A3B8"))
    app.setPalette(palette)

    # Qt 6.8+ can also be told directly not to follow the Windows dark mode.
    try:
        from PySide6.QtCore import Qt

        app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    except Exception:
        pass
