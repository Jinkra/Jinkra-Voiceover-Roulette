"""滚轮只滚动页面或选项列表。"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from ui_chrome import DoubleSpinBox, Dropdown, Slider, SpinBox


def scroll_down(app, widget):
    center = widget.rect().center()
    event = QWheelEvent(QPointF(center), QPointF(widget.mapToGlobal(center)),
                        QPoint(), QPoint(0, -120), Qt.NoButton, Qt.NoModifier,
                        Qt.NoScrollPhase, False)
    app.sendEvent(widget, event)
    return event


def main():
    app = QApplication([])
    dropdown = Dropdown()
    dropdown.setMaxVisibleItems(5)
    dropdown.addItems([f"选项 {i}" for i in range(30)])
    dropdown.resize(220, 35)
    dropdown.show()
    dropdown.setFocus()
    activated = []
    dropdown.activated.connect(activated.append)
    app.processEvents()

    assert not scroll_down(app, dropdown).isAccepted()
    QTest.keyClick(dropdown, Qt.Key_End)
    assert dropdown.currentIndex() == 0 and not activated
    QTest.keyClick(dropdown, Qt.Key_Down)
    QTest.qWait(500)
    view = dropdown.view()
    assert view.isVisible() and dropdown.currentIndex() == 0
    before = view.verticalScrollBar().value()
    scroll_down(app, view.viewport())
    assert view.verticalScrollBar().value() > before
    assert dropdown.currentIndex() == 0 and not activated

    item = view.indexAt(view.viewport().rect().center())
    assert item.isValid() and item.row() != 0
    QTest.mouseClick(view.viewport(), Qt.LeftButton, pos=view.visualRect(item).center())
    assert dropdown.currentIndex() == item.row() and activated == [item.row()]
    dropdown.close()

    for control in (Slider(Qt.Horizontal), SpinBox(), DoubleSpinBox()):
        control.setRange(0, 100)
        control.setValue(50)
        control.show()
        control.setFocus()
        app.processEvents()
        assert not scroll_down(app, control).isAccepted()
        assert control.value() == 50
        QTest.keyClick(control, Qt.Key_Right if isinstance(control, Slider) else Qt.Key_Up)
        assert control.value() > 50
        control.close()
    print("滚轮不会更改下拉框、滑块或数字框，展开的列表可以滚动并点击选择。")


if __name__ == "__main__":
    main()
