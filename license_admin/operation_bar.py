"""Persistent operation feedback without consuming header space."""

from __future__ import annotations

from time import monotonic

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from license_admin.accessibility import announce, set_accessible_text
from license_admin.localization import text
from license_admin.responsive import wrap_label


class OperationBar(QFrame):
    cancel_requested = Signal()
    retry_requested = Signal()
    dismiss_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("operationBar")
        self._started = 0.0
        self._elapsed = 0
        self._failed = False
        self._running = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)
        self.message_label = QLabel()
        self.message_label.setObjectName("busyStatus")
        self.message_label.setWordWrap(True)
        self.step_label = QLabel()
        self.step_label.setObjectName("operationStep")
        self.step_label.setWordWrap(True)
        for label in (self.message_label, self.step_label):
            wrap_label(label)
            label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.message_label)
        layout.addWidget(self.step_label)
        actions = QHBoxLayout()
        self.elapsed_label = QLabel()
        self.elapsed_label.setObjectName("operationElapsed")
        actions.addWidget(self.elapsed_label)
        actions.addStretch(1)
        self.cancel_button = QPushButton()
        self.cancel_button.clicked.connect(self.cancel_requested.emit)
        self.retry_button = QPushButton()
        self.retry_button.clicked.connect(self.retry_requested.emit)
        self.dismiss_button = QPushButton()
        self.dismiss_button.clicked.connect(self.dismiss_requested.emit)
        for button in (self.cancel_button, self.retry_button, self.dismiss_button):
            actions.addWidget(button)
            button.hide()
        layout.addLayout(actions)
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._update_elapsed)
        self.retranslate()
        self.hide()

    def retranslate(self) -> None:
        set_accessible_text(self.message_label, name=text("accessibility.application_status"))
        self.cancel_button.setText(text("common.cancel"))
        self.retry_button.setText(text("data.retry"))
        self.dismiss_button.setText(text("common.dismiss"))
        self._render_elapsed()

    def start(self, message: str, *, step: str = "", cancellable: bool = False) -> None:
        self._started = monotonic()
        self._elapsed = 0
        self._failed = False
        self._running = True
        self.message_label.setText(message)
        self.message_label.setAccessibleDescription(message)
        self.step_label.setText(step)
        self.step_label.setToolTip("")
        self.step_label.setVisible(bool(step))
        self.cancel_button.setEnabled(True)
        self.cancel_button.setVisible(cancellable)
        self.retry_button.hide()
        self.dismiss_button.hide()
        self._render_elapsed()
        self._timer.start()
        self.show()
        announce(self.message_label, " ".join(filter(None, (message, step))))

    def cancelling(self) -> None:
        self.cancel_button.setEnabled(False)
        self.step_label.setText(text("operation.cancelling"))
        self.step_label.show()
        announce(self.message_label, self.step_label.text())

    def show_error(self, error: str) -> None:
        self._failed = True
        self.message_label.setText(text("message.operation_failed"))
        self.message_label.setAccessibleDescription(error)
        self.step_label.setText(error[:200] + ("…" if len(error) > 200 else ""))
        self.step_label.setToolTip(error)
        self.step_label.show()
        self.cancel_button.hide()
        self.show()
        announce(self.message_label, text("message.operation_failed"), assertive=True)

    def finish(self) -> None:
        if self._running:
            self._update_elapsed()
        self._running = False
        self._timer.stop()
        if self._failed:
            self.retry_button.show()
            self.dismiss_button.show()
        else:
            self.hide()

    def dismiss(self) -> None:
        self._failed = False
        self.hide()

    def _update_elapsed(self) -> None:
        self._elapsed = int(monotonic() - self._started)
        self._render_elapsed()

    def _render_elapsed(self) -> None:
        duration = f"{self._elapsed // 60:02d}:{self._elapsed % 60:02d}"
        self.elapsed_label.setText(duration)
        self.elapsed_label.setAccessibleName(text("operation.elapsed", duration=duration))
