"""One-shot background worker for network operations."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QThread, Signal


class OperationThread(QThread):
    succeeded = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, operation: Callable[[], Any]) -> None:
        super().__init__()
        self._operation = operation

    def run(self) -> None:
        try:
            result = self._operation()
        except Exception as exc:  # surfaced to the GUI boundary
            if self.isInterruptionRequested():
                self.cancelled.emit()
            else:
                self.failed.emit(str(exc))
        else:
            if self.isInterruptionRequested():
                self.cancelled.emit()
            else:
                self.succeeded.emit(result)
