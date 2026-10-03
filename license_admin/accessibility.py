"""Small accessibility helpers shared by dashboard widgets."""

from __future__ import annotations

from PySide6.QtGui import QAccessible, QAccessibleAnnouncementEvent
from PySide6.QtWidgets import QWidget


def set_accessible_text(
    widget: QWidget,
    *,
    name: str,
    description: str = "",
) -> None:
    """Keep screen-reader text explicit when visible labels can disappear."""
    widget.setAccessibleName(name)
    widget.setAccessibleDescription(description)


def announce(
    widget: QWidget,
    message: str,
    *,
    assertive: bool = False,
) -> None:
    """Publish a live-region style announcement after visible state changes."""
    if not message.strip():
        return
    event = QAccessibleAnnouncementEvent(widget, message)
    event.setPoliteness(
        QAccessible.AnnouncementPoliteness.Assertive
        if assertive
        else QAccessible.AnnouncementPoliteness.Polite
    )
    QAccessible.updateAccessibility(event)
