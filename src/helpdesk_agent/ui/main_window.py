from __future__ import annotations

import threading

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ..agent.service import AgentEvent, AgentService
from ..config import INTENTS

SAMPLES = {
    "INTERNET_CONNECTIVITY": "There is something wrong with my internet.",
    "DNS_PROBLEM": "Websites are not resolving, but I can reach the network.",
    "IP_CONFIGURATION": "My computer got a strange IP and I cannot connect.",
    "WINDOWS_UPDATE": "Windows Update keeps failing.",
    "VPN_PROBLEM": "My VPN is not connecting.",
    "OTHER_UNKNOWN": "I have an IT problem that I cannot identify.",
    "PRINTER_PROBLEM": "The office printer is offline.",
    "FILE_FOLDER_PERMISSION": "I get access denied when opening a shared folder.",
    "NETWORK_ADAPTER": "My network adapter appears to be disabled.",
    "APPLICATION_NOT_RESPONDING": "An application is frozen and says not responding.",
    "REMOTE_DESKTOP": "I cannot connect to my office PC with Remote Desktop.",
    "WIFI_PROBLEM": "My Wi-Fi keeps disconnecting.",
    "HIGH_MEMORY_USAGE": "My computer is running out of RAM.",
    "WINDOWS_SERVICE": "A Windows service is not running.",
    "SYSTEM_INFORMATION": "I need to check my Windows and system information.",
    "HIGH_CPU_USAGE": "My CPU is stuck near 100 percent.",
    "DISK_SPACE": "My C drive is almost full.",
    "OUTLOOK_PROBLEM": "Outlook is not working correctly.",
}


class ApprovalBridge:
    def __init__(self) -> None:
        self.event = threading.Event()
        self.value = False

    def respond(self, value: bool) -> None:
        self.value = value
        self.event.set()


class AgentWorker(QThread):
    event_signal = Signal(object)
    approval_signal = Signal(object, str, str)
    finished_signal = Signal()

    def __init__(self, service: AgentService, problem: str, forced_intent: str | None) -> None:
        super().__init__()
        self.service = service
        self.problem = problem
        self.forced_intent = forced_intent
        self._approval: ApprovalBridge | None = None

    def run(self) -> None:
        try:
            self.service.run(
                self.problem,
                self.forced_intent,
                self._emit_event,
                self._request_approval,
            )
        finally:
            self.finished_signal.emit()

    def _emit_event(self, event: AgentEvent) -> None:
        self.event_signal.emit(event)

    def _request_approval(self, action: str, message: str, reason: str) -> bool:
        bridge = ApprovalBridge()
        self._approval = bridge
        self.approval_signal.emit(action, message, reason)
        bridge.event.wait()
        return bridge.value

    def respond_to_approval(self, approved: bool) -> None:
        if self._approval:
            self._approval.respond(approved)
            self._approval = None


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("IT Helpdesk • L1 Agent")
        self.setMinimumSize(920, 610)
        self.resize(980, 650)

        self.service = AgentService()
        self.worker: AgentWorker | None = None
        self.active_intent: str | None = None

        self._build_ui()
        self._apply_style()

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(16, 14, 16, 14)
        root_layout.setSpacing(10)

        # Header
        header = QFrame()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 2)
        title_box = QVBoxLayout()
        title = QLabel("IT Helpdesk")
        title.setObjectName("title")
        subtitle = QLabel("L1 AI Agent  •  Local-first diagnostics  •  Cloud → Local fallback")
        subtitle.setObjectName("subtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header_layout.addLayout(title_box)
        header_layout.addStretch()
        self.status = QLabel("READY")
        self.status.setObjectName("status")
        header_layout.addWidget(self.status, alignment=Qt.AlignmentFlag.AlignTop)
        root_layout.addWidget(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # Debug panel
        debug_panel = QFrame()
        debug_layout = QVBoxLayout(debug_panel)
        debug_layout.setContentsMargins(0, 0, 8, 0)
        debug_title = QLabel("Debug intents")
        debug_title.setObjectName("sectionTitle")
        debug_hint = QLabel("Click an intent to load a test case.")
        debug_hint.setWordWrap(True)
        debug_hint.setObjectName("hint")
        debug_layout.addWidget(debug_title)
        debug_layout.addWidget(debug_hint)

        self.active_label = QLabel("Active: AUTO")
        self.active_label.setObjectName("active")
        debug_layout.addWidget(self.active_label)

        clear_btn = QPushButton("Auto intent")
        clear_btn.clicked.connect(self.clear_intent)
        debug_layout.addWidget(clear_btn)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        buttons_host = QWidget()
        grid = QGridLayout(buttons_host)
        grid.setContentsMargins(0, 6, 0, 0)
        grid.setSpacing(6)
        for idx, intent in enumerate(INTENTS):
            button = QPushButton(intent.replace("_", " "))
            button.setToolTip(SAMPLES.get(intent, ""))
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.clicked.connect(lambda checked=False, x=intent: self.select_intent(x))
            grid.addWidget(button, idx // 2, idx % 2)
        scroll.setWidget(buttons_host)
        debug_layout.addWidget(scroll, stretch=1)

        # Chat panel
        chat_panel = QFrame()
        chat_layout = QVBoxLayout(chat_panel)
        chat_layout.setContentsMargins(8, 0, 0, 0)

        self.chat = QTextBrowser()
        self.chat.setOpenExternalLinks(False)
        self.chat.setPlaceholderText("Agent activity will appear here…")
        chat_layout.addWidget(self.chat, stretch=1)

        self.cwd_label = QLabel("Command working directory: the directory from which the app is launched")
        self.cwd_label.setObjectName("hint")
        chat_layout.addWidget(self.cwd_label)

        composer = QFrame()
        composer_layout = QHBoxLayout(composer)
        composer_layout.setContentsMargins(0, 6, 0, 0)
        self.input = QPlainTextEdit()
        self.input.setPlaceholderText("Describe the IT problem…")
        self.input.setFixedHeight(74)
        composer_layout.addWidget(self.input, stretch=1)
        send = QPushButton("Run Agent")
        send.setObjectName("send")
        send.setFixedWidth(110)
        send.clicked.connect(self.start_agent)
        composer_layout.addWidget(send, alignment=Qt.AlignmentFlag.AlignBottom)
        chat_layout.addWidget(composer)

        splitter.addWidget(debug_panel)
        splitter.addWidget(chat_panel)
        splitter.setSizes([250, 700])
        root_layout.addWidget(splitter, stretch=1)

        self.setCentralWidget(root)

    def _apply_style(self) -> None:
        self.setStyleSheet("""
            QWidget { background: #0f1115; color: #e7e9ee; font-family: Segoe UI; font-size: 10pt; }
            QFrame { background: #0f1115; }
            #title { font-size: 21px; font-weight: 700; color: #ffffff; }
            #subtitle { color: #9da4b0; margin-top: 1px; }
            #sectionTitle { font-size: 12px; font-weight: 700; color: #ffffff; }
            #hint { color: #858d9b; font-size: 9pt; }
            #active, #status { color: #b9c6ff; font-weight: 600; }
            #status { background: #1b2438; border-radius: 8px; padding: 6px 9px; }
            QTextBrowser { background: #151820; border: 1px solid #242a35; border-radius: 10px; padding: 12px; }
            QPlainTextEdit { background: #151820; border: 1px solid #2a303b; border-radius: 9px; padding: 8px; }
            QPushButton { background: #1a1f28; border: 1px solid #303743; border-radius: 7px; padding: 7px 8px; color: #e7e9ee; }
            QPushButton:hover { background: #222936; }
            QPushButton:pressed { background: #2a3140; }
            #send { background: #3d63d8; border: none; font-weight: 700; }
            #send:hover { background: #5074e4; }
            QScrollArea { background: transparent; }
        """)

    def clear_intent(self) -> None:
        self.active_intent = None
        self.active_label.setText("Active: AUTO")

    def select_intent(self, intent: str) -> None:
        self.active_intent = intent
        self.active_label.setText(f"Active: {intent}")
        self.input.setPlainText(SAMPLES.get(intent, ""))
        self.input.setFocus()

    def append(self, title: str, text: str) -> None:
        self.chat.append(f"<b>{title}</b><br>{_escape(text)}<br>")

    @Slot()
    def start_agent(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        problem = self.input.toPlainText().strip()
        if not problem:
            return

        self.append("You", problem)
        self.append("Agent", "Starting diagnosis…")
        self.status.setText("RUNNING")

        self.worker = AgentWorker(self.service, problem, self.active_intent)
        self.worker.event_signal.connect(self.on_event)
        self.worker.approval_signal.connect(self.on_approval)
        self.worker.finished_signal.connect(self.on_finished)
        self.worker.start()

    @Slot(object)
    def on_event(self, event: AgentEvent) -> None:
        labels = {
            "intent": "Intent",
            "status": "Agent",
            "model": "Model",
            "tool": "Tool",
            "tool_result": "Diagnostic Result",
            "resolved": "Resolved",
            "ask": "Need Information",
            "ticket": "Ticket",
            "error": "Error",
        }
        self.append(labels.get(event.kind, "Agent"), event.message)
        if event.kind == "ticket":
            self.status.setText("TICKET")
        elif event.kind == "resolved":
            self.status.setText("RESOLVED")

    @Slot(object, str, str)
    def on_approval(self, action: str, message: str, reason: str) -> None:
        answer = QMessageBox.question(
            self,
            "Approve system change",
            f"Action: {action}\n\n{message}\n\nReason: {reason}\n\nAllow this action to run?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if self.worker:
            self.worker.respond_to_approval(answer == QMessageBox.StandardButton.Yes)

    def on_finished(self) -> None:
        self.status.setText("READY" if self.status.text() == "RUNNING" else self.status.text())
        self.worker = None


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br>")
    )
