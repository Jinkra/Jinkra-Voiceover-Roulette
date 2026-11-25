"""Jinkra 的菜单与操作反馈。"""

import ctypes

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QPointF, QRectF, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractButton, QAbstractSlider, QAbstractSpinBox, QComboBox, QDoubleSpinBox,
    QLabel, QLineEdit, QMenu, QSlider, QSpinBox, QWidget, QWidgetAction,
)


def motion_allowed() -> bool:
    enabled = ctypes.c_int(1)
    result = ctypes.windll.user32.SystemParametersInfoW(
        0x1042, 0, ctypes.byref(enabled), 0  # SPI_GETCLIENTAREAANIMATION
    )
    return bool(enabled.value) if result else True


class Dropdown(QComboBox):
    """先打开选项列表，才允许更改当前值。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
QComboBox { combobox-popup: 0; padding-right: 30px; }
QComboBox::drop-down { subcontrol-origin: border; subcontrol-position: top right;
    width: 30px; border: none; background: transparent; }
QComboBox::down-arrow { image: none; width: 0; height: 0; }
""")

    def paintEvent(self, event):
        super().paintEvent(event)
        center = QPointF(self.width() - 17, self.height() / 2)
        chevron = QPainterPath(center + QPointF(-4, -2))
        chevron.lineTo(center + QPointF(0, 2))
        chevron.lineTo(center + QPointF(4, -2))
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor("#315e59" if self.isEnabled() else "#82948d"), 1.5)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawPath(chevron)

    def mousePressEvent(self, event):
        if not self.isEditable() and event.button() == Qt.LeftButton:
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if not self.isEditable() and event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.showPopup()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        # 让设置页接管滚动，避免鼠标经过下拉框时改动配置。
        event.ignore()

    def keyPressEvent(self, event):
        if self.view().isVisible() or self.isEditable():
            super().keyPressEvent(event)
            return
        key = event.key()
        if key in (Qt.Key_Space, Qt.Key_F4, Qt.Key_Up, Qt.Key_Down):
            self.showPopup()
            event.accept()
        elif key in (Qt.Key_Home, Qt.Key_End, Qt.Key_PageUp, Qt.Key_PageDown) or event.text().isprintable():
            event.ignore()
        else:
            super().keyPressEvent(event)


class Slider(QSlider):
    def wheelEvent(self, event):
        event.ignore()


class SpinBox(QSpinBox):
    def wheelEvent(self, event):
        event.ignore()


class DoubleSpinBox(QDoubleSpinBox):
    def wheelEvent(self, event):
        event.ignore()


class ButtonFeedback(QObject):
    """为现有 Qt 按钮保留原生输入和焦点，叠加短促的轮廓反馈。"""

    _controls = (QAbstractButton, QAbstractSlider, QAbstractSpinBox, QComboBox)

    def __init__(self, application, enabled) -> None:
        super().__init__(application)
        self.enabled = enabled
        self.system_motion = motion_allowed()
        application.installEventFilter(self)

    def eventFilter(self, widget, event) -> bool:
        binding_field = isinstance(widget, QLineEdit) and widget.property("jinkra_key_capture")
        if not binding_field and not isinstance(widget, self._controls):
            return False
        kind = event.type()
        effect = getattr(widget, "_jinkra_feedback", None)
        if kind == QEvent.Resize and effect is not None:
            effect.setGeometry(widget.rect())
            return False
        if kind in (QEvent.Hide, QEvent.FocusOut, QEvent.EnabledChange) and effect is not None:
            effect.clear()
            return False
        if not self.system_motion or not self.enabled() or not widget.isEnabled():
            return False
        if kind in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
            if event.button() != Qt.MouseButton.LeftButton:
                return False
        elif kind in (QEvent.KeyPress, QEvent.KeyRelease):
            if event.isAutoRepeat():
                return False
            if not binding_field and event.key() not in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
                return False
        elif kind not in (QEvent.Enter, QEvent.Leave):
            return False
        if effect is None:
            effect = _Feedback(widget)
            widget._jinkra_feedback = effect
        if kind in (QEvent.MouseButtonPress, QEvent.KeyPress):
            effect.animate(0.85, 65)
        elif kind == QEvent.Enter:
            effect.animate(0.24, 120)
        else:
            effect.animate(0.0, 170)
        return False


class _Feedback(QWidget):
    def __init__(self, control) -> None:
        super().__init__(control)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.NoFocus)
        self.setGeometry(control.rect())
        self.amount = 0.0
        self.anim = QVariantAnimation(self)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim.valueChanged.connect(self._apply)
        self.hide()

    def animate(self, target, duration) -> None:
        self.anim.stop()
        self.anim.setStartValue(self.amount)
        self.anim.setEndValue(target)
        self.anim.setDuration(duration)
        self.anim.start()

    def clear(self) -> None:
        self.anim.stop()
        self._apply(0.0)

    def _apply(self, value) -> None:
        self.amount = float(value)
        if self.amount > 0.01:
            self.show()
            self.update()
        else:
            self.hide()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(52, 154, 137, int(125 * self.amount)), 1.2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5), 6, 6)


def branded_menu(parent=None, heading: str = "") -> QMenu:
    menu = QMenu(parent)
    menu.setStyleSheet('''
QMenu {
    background: #202322; color: #f1f0e9; padding: 6px;
    border: 1px solid #414743; border-radius: 9px; font-size: 13px;
}
QMenu::item { padding: 8px 24px 8px 16px; border-radius: 5px; }
QMenu::item:selected { background: #354640; color: #effcf4; }
QMenu::item:disabled { color: #9a9e97; }
QMenu::separator { height: 1px; background: #404542; margin: 5px 7px; }
QMenu QLabel { color: #a9d8ca; padding: 8px 10px 5px; font-weight: 700; }
''')
    if heading:
        title = QWidgetAction(menu)
        title.setDefaultWidget(QLabel(heading, menu))
        menu.addAction(title)
        menu.addSeparator()
    return menu
