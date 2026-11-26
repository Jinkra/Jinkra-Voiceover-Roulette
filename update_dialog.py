"""在工作线程检查发布、测试下载线路及准备更新。"""

import sys
import threading

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QProgressBar, QPushButton, QVBoxLayout,
)

import updates


class UpdateDialog(QDialog):
    checked = Signal(object)
    tested = Signal(object)
    progress = Signal(object, object)
    ready = Signal(object)
    failed = Signal(str)

    def __init__(self, service, parent=None):
        super().__init__(parent)
        self.service = service
        self.busy = False
        self.release = None
        self.staged = None
        self.setWindowTitle("检查 Jinkra 更新")
        self.setWindowIcon(service.make_icon())
        self.resize(515, 395)
        layout = QVBoxLayout(self)
        self.header = QLabel(f"当前版本  {service.APP_VERSION}")
        self.header.setTextFormat(Qt.PlainText)
        layout.addWidget(self.header)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.PlainText)
        layout.addWidget(self.status)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log, 1)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setAlignment(Qt.AlignCenter)
        # 全局主题会把文字设成浅色，落在浅色进度条上看不清：这里固定成深色字、浅色进度块。
        self.bar.setStyleSheet(
            "QProgressBar { color: #1f2b25; background: #e4ebe6; border: 1px solid #b9c9c0;"
            " border-radius: 5px; min-height: 20px; font-weight: 600; }"
            "QProgressBar::chunk { background: #9ed3bb; border-radius: 4px; }")
        self.bar.hide()
        layout.addWidget(self.bar)

        buttons = QHBoxLayout()
        self.release_page = QPushButton("打开发布页")
        self.release_page.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(updates.RELEASES)))
        self.test = QPushButton("测试线路")
        self.test.clicked.connect(self._test)
        self.check = QPushButton("重新检查")
        self.check.clicked.connect(self._check)
        self.download = QPushButton("下载更新")
        self.download.clicked.connect(self._download_or_apply)
        buttons.addWidget(self.release_page)
        buttons.addStretch()
        for button in (self.test, self.check, self.download):
            buttons.addWidget(button)
        layout.addLayout(buttons)

        self.checked.connect(self._on_checked)
        self.tested.connect(self._on_tested)
        self.progress.connect(self._on_progress)
        self.ready.connect(self._on_ready)
        self.failed.connect(self._on_failed)
        self._check()

    def _work(self, callback, completed):
        self.busy = True
        self._buttons()
        def run():
            try:
                completed.emit(callback())
            except Exception as error:
                self.failed.emit(str(error))
        threading.Thread(target=run, daemon=True).start()

    def _buttons(self):
        newer = self.release is not None and (
            updates.version_tuple(self.release.version) > updates.version_tuple(self.service.APP_VERSION))
        self.test.setEnabled(not self.busy and self.release is not None)
        self.check.setEnabled(not self.busy and self.staged is None)
        self.download.setEnabled(not self.busy and newer and getattr(sys, "frozen", False))

    def _check(self):
        self.log.clear()
        self.bar.hide()
        self.release = None
        self.status.setText("正在获取 GitHub 官方发布信息…")
        self._work(lambda: updates.check("v0.0.0"), self.checked)

    def _on_checked(self, release):
        self.release = release
        self.busy = False
        if release is None:
            self.status.setText("仓库还没有正式发布。")
        elif updates.version_tuple(release.version) <= updates.version_tuple(self.service.APP_VERSION):
            self.status.setText("当前已是最新版本。可测试各条下载线路。")
        else:
            self.status.setText(f"发现新版 {release.version}。")
        if release is not None and release.notes:
            self.log.setPlainText(release.notes)
        self._buttons()

    def _test(self):
        self.log.clear()
        self.status.setText("正在测试真实发布包的下载线路…")
        self._work(lambda: updates.probe_routes(self.release, self._route), self.tested)

    def _route(self, name, elapsed):
        self.progress.emit(f"{name}：{round(elapsed * 1000)} ms" if elapsed is not None
                           else f"{name}：不可用", None)

    def _on_tested(self, routes):
        self.busy = False
        self.status.setText(f"首选线路：{routes[0][0]}" if routes else "所有线路暂不可用。")
        self._buttons()

    def _download_or_apply(self):
        if self.staged is not None:
            try:
                updates.apply_update(self.staged)
            except OSError as error:
                self._on_failed(str(error))
                return
            self.accept()
            # 不能用 QApplication.quit()：Qt 6 会先逐个关窗口，设置窗口为了淡出动画
            # 会先拒绝关闭，整个退出就被取消，旧版一直不退，更新程序只好干等。
            # exit() 直接结束事件循环，不经过关窗确认。
            from PySide6.QtCore import QCoreApplication
            QCoreApplication.exit(0)
            return
        self.log.clear()
        self.status.setText("正在自动选择线路并校验更新包…")
        self.bar.setValue(0)
        self.bar.show()
        self._work(lambda: updates.download(self.release, self.service.BASE_DIR, self.progress.emit),
                   self.ready)

    def _on_progress(self, text, percent):
        if text is not None:
            self.log.appendPlainText(str(text))
        if percent is not None:
            self.bar.setValue(int(percent))

    def _on_ready(self, staged):
        self.busy = False
        self.staged = staged
        self.status.setText("下载及校验完成。重启后会更新程序，音效和设置保留在原目录。")
        self.download.setText("更新并重启")
        self._buttons()

    def _on_failed(self, message):
        self.busy = False
        self.status.setText("本次检查或更新未能完成。")
        self.log.appendPlainText(message)
        self._buttons()

    def reject(self):
        if self.busy:
            return
        if self.staged is not None:
            import shutil
            shutil.rmtree(self.staged.parent, ignore_errors=True)
            self.staged = None
        super().reject()

    def closeEvent(self, event):
        if self.busy:
            event.ignore()
        else:
            super().closeEvent(event)

