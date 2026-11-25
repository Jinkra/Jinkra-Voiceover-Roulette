"""Jinkra 首次启动、激活与设备设置向导。"""

import time

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFrame, QGraphicsOpacityEffect, QHBoxLayout,
    QLabel, QLineEdit, QListView, QProgressBar, QPushButton, QSplashScreen, QStackedWidget,
    QVBoxLayout, QWidget,
)

import driver_setup
from ui_chrome import motion_allowed


def reveal(widget, enabled=True):
    if not enabled or not motion_allowed():
        return
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    animation = QPropertyAnimation(effect, b"opacity", effect)
    animation.setDuration(180)
    animation.setStartValue(0.58)
    animation.setEndValue(1.0)
    animation.setEasingCurve(QEasingCurve.OutCubic)
    effect.animation = animation

    def finish():
        if widget.graphicsEffect() is effect:
            widget.setGraphicsEffect(None)

    animation.finished.connect(lambda: QTimer.singleShot(0, finish))
    animation.start()


def splash(icon, version, animated=True):
    canvas = QPixmap(380, 205)
    canvas.fill(QColor("#222725"))
    painter = QPainter(canvas)
    painter.drawPixmap(159, 23, icon.pixmap(62, 62))
    painter.setPen(QColor("#f2f1e9"))
    painter.setFont(QFont("Segoe UI", 15, QFont.DemiBold))
    painter.drawText(canvas.rect().adjusted(12, 101, -12, -65), Qt.AlignHCenter, "Jinkra Voiceover Roulette")
    painter.setFont(QFont("Microsoft YaHei UI", 9))
    painter.setPen(QColor("#abc9bc"))
    painter.drawText(canvas.rect().adjusted(12, 150, -12, -17), Qt.AlignHCenter,
                     f"正在启动  ·  {version}")
    painter.end()
    screen = QSplashScreen(canvas)
    screen.setWindowFlag(Qt.WindowStaysOnTopHint, True)
    screen.show()
    if animated and motion_allowed():
        motion = QPropertyAnimation(screen, b"windowOpacity", screen)
        motion.setStartValue(0.55)
        motion.setEndValue(1.0)
        motion.setDuration(180)
        motion.start()
        screen.motion = motion
    return screen


class SetupGuide(QDialog):
    def __init__(self, service, activation, cfg, parent=None):
        super().__init__(parent)
        self.service = service
        self.activation = activation
        self.cfg = cfg
        self.preferred_mic = str(cfg.get("mic_device") or "")
        self.unlocked = activation.active()
        self.activation_only = not self.unlocked and bool(cfg.get("guide_completed"))
        self.failures = 0
        self.locked_until = 0.0
        self.retry_timer = QTimer(self, interval=250)
        self.retry_timer.timeout.connect(self._retry_status)
        self.setWindowTitle("Jinkra · 使用向导")
        self.setWindowIcon(service.make_icon())
        self.resize(780, 535)
        self.setMinimumSize(690, 475)
        self.setStyleSheet("""
QDialog { background: #f4f4ec; color: #252f29; font-family: "Microsoft YaHei UI"; }
QFrame#GuideRail { background: #242a26; border-radius: 12px; }
QLabel { color: #304137; font-size: 13px; }
QLabel#RailBrand { color: #f1f2e9; font-size: 19px; font-weight: 700; }
QLabel#Step { color: #b9d5c6; font-size: 13px; }
QLabel#Title { color: #222c25; font-size: 27px; font-weight: 700; }
QLabel#GuideNote { color: #326456; font-size: 12px; }
QLabel#ActivationBrand { color: #233832; font-size: 14px; font-weight: 700; }
QLabel#ActivationTitle { color: #172e27; font-size: 32px; font-weight: 700; }
QLabel#ActivationMuted { color: #52685f; font-size: 13px; }
QLabel#ActivationLabel { color: #253d33; font-size: 13px; font-weight: 700; }
QLabel#ActivationAccount { color: #1b3b2e; font-size: 20px; font-weight: 700; }
QLabel#ActivationFeedback { color: #93452e; font-size: 12px; }
QFrame#ActivationCard { background: #e9f2ed; border: 1px solid #d6e5db; border-radius: 16px; }
QFrame#ActivationDivider { background: #dce5db; }
QPushButton, QLineEdit, QComboBox { min-height: 26px; background: #ffffff; border: 1px solid #cbd4c8;
    border-radius: 7px; padding: 5px 12px; font-size: 13px; color: #29362d; }
QPushButton:hover, QLineEdit:focus, QComboBox:focus { border-color: #52907c; background: #f2f8ef; }
QPushButton:pressed { background: #cde4d6; }
QPushButton#Next { background: #316d5c; color: #ffffff; border-color: #316d5c; font-weight: 700; }
QPushButton#Next:hover { background: #285a4c; }
QLineEdit#ActivationCode, QPushButton#Activate { min-height: 32px; border-radius: 9px; }
QPushButton#Activate { background: #205e49; border-color: #205e49; color: #ffffff; font-weight: 700; }
QPushButton#Activate:hover { background: #194d3c; }
QPushButton#Activate:pressed { background: #123b2d; }
QPushButton#Activate:focus { border-color: #78b69a; }
QPushButton#Activate:disabled { color: #526b61; background: #e2ebe4; border-color: #d8e4dc; }
QPushButton:disabled { color: #859087; background: #e8ebe3; border-color: #d8dfd5; }
QComboBox#GuideMic { combobox-popup: 0; }
QComboBox#GuideMic:disabled { color: #576b60; background: #e9ede6; }
QListView#GuideMicOptions { color: #223b30; background: #ffffff; outline: 0;
    border: 1px solid #bacfc3; border-radius: 7px; padding: 3px;
    selection-color: #133d2b; selection-background-color: #dceee3; }
QListView#GuideMicOptions::item { min-height: 28px; padding: 3px 8px; }
QListView#GuideMicOptions::item:hover { background: #edf5ef; }
QListView#GuideMicOptions::item:selected { background: #dceee3; color: #133d2b; }
QProgressBar { background: #49574f; border: none; border-radius: 2px; }
QProgressBar::chunk { background: #9ed3bb; border-radius: 2px; }
""")
        outer = QHBoxLayout(self)
        outer.setContentsMargins(15, 15, 15, 15)
        outer.setSpacing(23)
        rail = self.rail = QFrame()
        rail.setObjectName("GuideRail")
        rail.setFixedWidth(172)
        layout = QVBoxLayout(rail)
        layout.setContentsMargins(15, 17, 15, 17)
        layout.setSpacing(11)
        logo = QLabel()
        logo.setPixmap(service.make_icon().pixmap(54, 54))
        layout.addWidget(logo)
        label = QLabel("Jinkra\nVoiceover\nRoulette")
        label.setObjectName("RailBrand")
        layout.addWidget(label)
        layout.addSpacing(16)
        self.step = QLabel()
        self.step.setObjectName("Step")
        layout.addWidget(self.step)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        self.progress.setRange(0, 4)
        layout.addWidget(self.progress)
        layout.addStretch()
        outer.addWidget(rail)

        right = QVBoxLayout()
        right.setContentsMargins(0, 8, 7, 5)
        right.setSpacing(14)
        outer.addLayout(right, 1)
        self.pages = QStackedWidget()
        right.addWidget(self.pages, 1)

        self.pages.addWidget(self._activation_page())

        essentials = self._page("用轮盘播放音效", "短按呼出键播放上次选中的音效。长按后用鼠标选中扇区，松手播放。")
        essentials.insertWidget(2, self._text(
            f"当前呼出键  {service.spec_label(str(cfg['hotkey']))}\n"
            "双击音效库里的项目可试听，拖到轮盘即可上盘。"
            "\n启动后，快捷键与轮盘外观都可以继续调整。", note=True))

        mic = self._page("设置语音输出", "将你的麦克风与音效混合，供游戏或聊天软件录制。也可以先只使用本地播放。")
        self.mic_picker = QComboBox()
        self.mic_picker.setObjectName("GuideMic")
        self.mic_picker.setAccessibleName("实体麦克风")
        self.mic_picker.activated.connect(self._remember_mic)
        options = QListView()
        options.setObjectName("GuideMicOptions")
        options.setMouseTracking(True)
        self.mic_picker.setView(options)
        mic_label = QLabel("实体麦克风")
        mic_label.setBuddy(self.mic_picker)
        mic.insertWidget(2, mic_label)
        mic.insertWidget(3, self.mic_picker)
        self.mic_status = self._text("请检查麦克风连接和 Windows 麦克风权限，再点击「重新检测」。", note=True)
        mic.insertWidget(4, self.mic_status)
        self.enable_mic = QCheckBox("通过 Jinkra Virtual Mic 向游戏送声")
        self.enable_mic.setChecked(bool(cfg.get("mic_enabled", False)))
        mic.insertWidget(5, self.enable_mic)
        self.driver_status = self._text("", note=True)
        mic.insertWidget(6, self.driver_status)
        actions = QHBoxLayout()
        self.btn_install = QPushButton("安装随附驱动")
        self.btn_install.clicked.connect(self._install)
        self.btn_refresh = QPushButton("重新检测")
        self.btn_refresh.clicked.connect(self._refresh_audio)
        actions.addWidget(self.btn_install)
        actions.addWidget(self.btn_refresh)
        actions.addStretch()
        mic.insertLayout(7, actions)

        done = self._page("准备好了", "进入工作台后，音效库、轮盘设置和语音输出都可以随时更改。")
        self.summary = self._text("", note=True)
        done.insertWidget(2, self.summary)

        self.footer = QWidget()
        footer = QHBoxLayout(self.footer)
        footer.setContentsMargins(0, 0, 0, 0)
        self.prev = QPushButton("上一步")
        self.prev.clicked.connect(lambda: self._show(self.pages.currentIndex() - 1))
        self.skip = QPushButton("暂用本地播放")
        self.skip.clicked.connect(lambda: self._finish(local_only=True))
        self.next = QPushButton("激活")
        self.next.setObjectName("Next")
        self.next.clicked.connect(self._advance)
        footer.addWidget(self.prev)
        footer.addStretch()
        footer.addWidget(self.skip)
        footer.addWidget(self.next)
        right.addWidget(self.footer)
        self.detect_timer = QTimer(self, interval=1800)
        self.detect_timer.timeout.connect(self._refresh_audio)
        self._show(1 if self.unlocked else 0)

    def _activation_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 12, 24, 20)
        layout.setSpacing(18)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(self.windowIcon().pixmap(34, 34))
        brand.addWidget(logo)
        name = QLabel("Jinkra Voiceover Roulette")
        name.setObjectName("ActivationBrand")
        brand.addWidget(name)
        brand.addStretch()
        layout.addLayout(brand)
        divider = QFrame()
        divider.setObjectName("ActivationDivider")
        divider.setFixedHeight(1)
        layout.addWidget(divider)

        body = QHBoxLayout()
        body.setSpacing(36)
        form = QVBoxLayout()
        form.setSpacing(10)
        form.addStretch(2)
        form.addWidget(self._text("激活音效轮盘", style="ActivationTitle"))
        form.addWidget(self._text("用微信扫码获取激活码，然后在这里输入。", style="ActivationMuted"))
        form.addSpacing(12)
        self.code = QLineEdit()
        self.code.setObjectName("ActivationCode")
        self.code.setEchoMode(QLineEdit.Password)
        self.code.setMaxLength(128)
        self.code.setPlaceholderText("粘贴激活码")
        self.code.setAccessibleName("激活码")
        self.code.returnPressed.connect(self._advance)
        code_label = self._text("激活码", style="ActivationLabel")
        code_label.setBuddy(self.code)
        form.addWidget(code_label)
        form.addWidget(self.code)
        self.activate_button = QPushButton("激活" if self.activation_only else "激活并继续")
        self.activate_button.setObjectName("Activate")
        self.activate_button.setEnabled(False)
        self.activate_button.clicked.connect(self._advance)
        self.code.textChanged.connect(self._update_activate_button)
        form.addWidget(self.activate_button)
        self.activation_message = self._text("", style="ActivationFeedback")
        self.activation_message.setMinimumHeight(36)
        self.activation_message.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        form.addWidget(self.activation_message)
        form.addStretch(2)
        body.addLayout(form, 1)

        card = QFrame()
        card.setObjectName("ActivationCard")
        card.setMinimumWidth(220)
        card.setMaximumWidth(258)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 20, 22, 19)
        card_layout.setSpacing(7)
        channel = self._text("微信公众号", style="ActivationMuted")
        channel.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(channel)
        account = self._text("都拓文化", style="ActivationAccount")
        account.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(account)
        qr = QLabel()
        qr.setAccessibleName("都拓文化微信公众号二维码")
        qr.setAlignment(Qt.AlignCenter)
        poster = QPixmap(str(self.service.RESOURCE_DIR / "wechat-promotion.png"))
        if poster.isNull():
            qr.setText("二维码暂不可用")
        else:
            # 原图二维码四周的留白要一起保留，方便扫码。
            qr.setPixmap(poster.copy(73, 73, 460, 460).scaled(
                158, 158, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        card_layout.addSpacing(4)
        card_layout.addWidget(qr)
        hint = self._text("也可在微信搜索公众号", style="ActivationMuted")
        hint.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(hint)
        body.addWidget(card, 0, Qt.AlignVCenter)
        layout.addLayout(body, 1)
        return page

    def _update_activate_button(self):
        self.activate_button.setEnabled(bool(self.code.text().strip()) and not self.retry_timer.isActive())

    def _text(self, value, note=False, style=""):
        label = QLabel(value)
        label.setWordWrap(True)
        label.setTextFormat(Qt.PlainText)
        label.setObjectName("GuideNote" if note else style)
        return label

    def _page(self, title, explanation):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        label = self._text(title)
        label.setObjectName("Title")
        layout.addWidget(label)
        layout.addWidget(self._text(explanation))
        layout.addStretch()
        self.pages.addWidget(page)
        return layout

    def _show(self, index):
        if not 0 <= index < self.pages.count() or (index > 0 and not self.unlocked):
            return
        if index != 2:
            self.detect_timer.stop()
        if index == 2:
            self._refresh_audio()
            self.detect_timer.start()
        if index == 3:
            self.summary.setText("游戏语音已选中。进入游戏后请选择 Jinkra Virtual Mic。"
                                 if self.enable_mic.isEnabled() and self.enable_mic.isChecked()
                                 else "将使用本地播放。虚拟麦克风可在「语音输出」中补设。")
        self.pages.setCurrentIndex(index)
        self.rail.setVisible(index != 0)
        self.footer.setVisible(index != 0)
        self.progress.setValue(index + 1)
        self.step.setText(f"{index + 1} / 4\n" + ("激活", "轮盘入门", "语音设备", "进入工作台")[index])
        self.prev.setVisible(index > 1)
        self.skip.setVisible(index in (1, 2))
        self.next.setText("进入工作台" if index == 3 else "下一步")
        if index == 0:
            self.code.setFocus()
        reveal(self.pages, self.cfg.get("animations", True))

    def _refresh_audio(self):
        service = self.service
        picker = self.mic_picker
        if not picker.view().isVisible():
            choices = list(dict.fromkeys(device.description() for device in service.real_inputs()))
            if not picker.count() or [picker.itemData(i) for i in range(1, picker.count())] != choices:
                picker.clear()
                if choices:
                    picker.addItem("自动选择实体麦克风", "")
                    for name in choices:
                        picker.addItem(name, name)
                    picker.setCurrentIndex(max(0, picker.findData(self.preferred_mic)))
                else:
                    picker.addItem("未检测到实体麦克风")
            picker.setEnabled(bool(choices))
            self.mic_status.setVisible(not choices)
        ready = service.guess_virtual_output() is not None
        present = driver_setup.installer(service.BASE_DIR, service.RESOURCE_DIR)
        self.enable_mic.setEnabled(ready)
        self.btn_install.setVisible(not ready and present is not None)
        self.driver_status.setText("已识别 Jinkra Virtual Mic。请在游戏里选择这个录音设备。"
                                   if ready else "已找到随附驱动。安装后可重新检测录音设备。"
                                   if present else "当前包没有随附已签名的虚拟麦克风驱动，可先使用本地播放。")

    def _remember_mic(self, index):
        self.preferred_mic = str(self.mic_picker.itemData(index) or "")

    def _install(self):
        try:
            driver_setup.start_install(self.service.BASE_DIR, self.service.RESOURCE_DIR)
        except OSError as error:
            self.driver_status.setText(str(error))

    def _retry_status(self):
        left = int(self.locked_until - time.monotonic() + 0.99)
        if left <= 0:
            self.retry_timer.stop()
            self._update_activate_button()
            self.activation_message.clear()
        else:
            self.activation_message.setText(f"请在 {left} 秒后重试。")

    def _advance(self):
        index = self.pages.currentIndex()
        if index == 0:
            if self.retry_timer.isActive() or not self.code.text().strip():
                return
            try:
                self.unlocked = self.activation.activate(self.code.text())
            except OSError as error:
                self.activation_message.setText(str(error))
                return
            self.code.clear()
            if not self.unlocked:
                self.failures += 1
                self.activation_message.setText("激活码不正确，请核对公众号提供的内容。")
                if self.failures == 5:
                    self.failures = 0
                    self.locked_until = time.monotonic() + 30
                    self.retry_timer.start()
                    self._update_activate_button()
                    self._retry_status()
                return
            if self.activation_only:
                self.accept()
                return
        if index == 3:
            self._finish()
        else:
            self._show(index + 1)

    def _finish(self, local_only=False):
        self.cfg["guide_completed"] = True
        self.cfg["help_tip_shown"] = True
        if self.mic_picker.currentData() is not None:
            self.cfg["mic_device"] = str(self.mic_picker.currentData() or "")
        self.cfg["mic_enabled"] = bool(not local_only and self.enable_mic.isEnabled()
                                       and self.enable_mic.isChecked())
        self.service.save_config(self.cfg)
        self.accept()

