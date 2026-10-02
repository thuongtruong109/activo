"""Blurred, dimmed backdrop used while a modal dialog is active."""

from __future__ import annotations

from types import TracebackType

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsBlurEffect,
    QMainWindow,
    QWidget,
)


class ModalBackdrop:
    """Temporarily blur a window's content and block its surface."""

    def __init__(
        self,
        host: QMainWindow,
        *,
        blur_radius: float = 9.0,
    ) -> None:
        self._host = host
        self._blur_radius = blur_radius
        self._target: QWidget | None = None
        self._blur: QGraphicsBlurEffect | None = None
        self._overlay: QFrame | None = None

    def __enter__(self) -> ModalBackdrop:
        target = self._host.centralWidget()
        if target is None:
            return self

        self._target = target
        self._blur = QGraphicsBlurEffect(target)
        self._blur.setBlurRadius(self._blur_radius)
        self._blur.setBlurHints(
            QGraphicsBlurEffect.BlurHint.QualityHint
            | QGraphicsBlurEffect.BlurHint.AnimationHint
        )
        target.setGraphicsEffect(self._blur)

        self._overlay = QFrame(self._host)
        self._overlay.setObjectName("modalBackdrop")
        self._overlay.setGeometry(self._host.rect())
        self._overlay.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            False,
        )
        self._overlay.show()
        self._overlay.raise_()
        QApplication.processEvents()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._overlay is not None:
            self._overlay.hide()
            self._overlay.deleteLater()
            self._overlay = None
        if self._blur is not None:
            self._blur.setEnabled(False)
            self._blur.deleteLater()
        self._target = None
        self._blur = None
