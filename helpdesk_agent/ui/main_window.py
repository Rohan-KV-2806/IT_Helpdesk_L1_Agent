from __future__ import annotations

import html
import json
import threading

from PySide6.QtCore import QThread, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ..agent.service import AgentEvent, AgentService, ApprovalResponse
from ..notifications.email import is_valid_email
from ..settings import load_settings, normalize_backend
from .ai_settings_dialog import AISettingsDialog


class ApprovalBridge:
    def __init__(self):
        self.event = threading.Event()
        self.value = ApprovalResponse("no", "")

    def respond(self, value: ApprovalResponse):
        self.value = value
        self.event.set()


class AgentWorker(QThread):
    event_signal = Signal(object)
    approval_signal = Signal(object, str, str)
    user_decision_signal = Signal(object, str, str)
    finished_signal = Signal()

    def __init__(self, service: AgentService, problem: str, backend: str):
        super().__init__()
        self.service = service
        self.problem = problem
        self.backend = backend
        self._approval: ApprovalBridge | None = None

    def run(self):
        try:
            self.service.run(
                self.problem,
                self.backend,
                self.event_signal.emit,
                self._request_approval,
                self._request_user_decision,
            )
        finally:
            self.finished_signal.emit()

    def _request_approval(self, action: str, message: str, reason: str) -> ApprovalResponse:
        bridge = ApprovalBridge()
        self._approval = bridge
        self.approval_signal.emit(action, message, reason)
        while not bridge.event.wait(0.25):
            if self.isInterruptionRequested():
                bridge.respond(ApprovalResponse("no", "Window closed; do not execute the proposed change."))
                break
        self._approval = None
        return bridge.value

    def _request_user_decision(self, action: str, message: str, reason: str) -> ApprovalResponse:
        bridge = ApprovalBridge()
        self._approval = bridge
        self.user_decision_signal.emit(action, message, reason)
        while not bridge.event.wait(0.10):
            if self.isInterruptionRequested():
                bridge.respond(ApprovalResponse("no", "Window closed; do not make a change."))
                break
        self._approval = None
        return bridge.value

    def respond_to_approval(self, response: ApprovalResponse):
        if self._approval:
            self._approval.respond(response)


class DecisionDialog(QDialog):
    def __init__(self, parent, action: str, message: str, reason: str):
        super().__init__(parent)
        self.is_resolution_confirmation = action == "CONFIRM_RESOLUTION"
        self.is_user_decision = action == "ASK_USER"
        if self.is_resolution_confirmation:
            self.setWindowTitle("Problem Solved?")
        elif self.is_user_decision:
            self.setWindowTitle("L1 Agent Needs Your Input")
        else:
            self.setWindowTitle("L1 Fix Decision")
        self.setModal(True)
        self.setMinimumWidth(520)
        self.choice = ApprovalResponse("no", "")

        layout = QVBoxLayout(self)
        if self.is_resolution_confirmation:
            title = QLabel("Is your problem solved?")
            body_text = f"{message}\n\nReason: {reason}\n\nPlease confirm whether the original problem is actually gone."
        elif self.is_user_decision:
            title = QLabel("I need your input")
            body_text = f"{message}\n\nReason: {reason}\n\nYes = follow the suggested option. No = do not use it. Your idea = tell the agent what you want instead."
        else:
            title = QLabel(f"Proposed action: {action}")
            body_text = f"{message}\n\nReason: {reason}\n\nAllow this action to run?"
        title.setStyleSheet("font-weight: 650; font-size: 14px;")
        layout.addWidget(title)

        body = QLabel(body_text)
        body.setWordWrap(True)
        layout.addWidget(body)

        self.idea = QPlainTextEdit()
        if self.is_resolution_confirmation:
            self.idea.setPlaceholderText("Tell the L1 agent what is still wrong or what you want it to try next…")
        elif self.is_user_decision:
            self.idea.setPlaceholderText("For example: check Teams, use Firefox, or run the temp cleanup…")
        else:
            self.idea.setPlaceholderText("Tell the L1 agent what you want it to consider instead…")
        self.idea.setFixedHeight(75)
        layout.addWidget(self.idea)

        row = QHBoxLayout()
        yes = QPushButton("Yes")
        no = QPushButton("No")
        idea = QPushButton("Your idea")
        yes.clicked.connect(self._yes)
        no.clicked.connect(self._no)
        idea.clicked.connect(self._idea)
        row.addStretch()
        row.addWidget(yes)
        row.addWidget(no)
        row.addWidget(idea)
        layout.addLayout(row)

    def _yes(self):
        self.choice = ApprovalResponse("yes", "")
        self.accept()

    def _no(self):
        self.choice = ApprovalResponse("no", "")
        self.accept()

    def _idea(self):
        text = self.idea.toPlainText().strip()
        if not text:
            QMessageBox.information(self, "Your idea", "Enter an instruction for the L1 agent first.")
            return
        self.choice = ApprovalResponse("idea", text)
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("L1 Agent")
        self.setMinimumSize(760, 560)
        self.settings = load_settings()
        self.service = AgentService()
        self.worker: AgentWorker | None = None
        self._build_ui()
        self._style()

    def _build_ui(self):
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(9)

        title_row = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("L1 IT Helpdesk Agent")
        title.setObjectName("title")
        subtitle = QLabel("Windows L1 troubleshooting • support escalation • guided fixes")
        subtitle.setObjectName("subtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        title_row.addLayout(title_box)
        title_row.addStretch()
        close_btn = QPushButton("×")
        close_btn.setObjectName("closeButton")
        close_btn.setFixedSize(38, 34)
        close_btn.clicked.connect(self.close)
        title_row.addWidget(close_btn)
        layout.addLayout(title_row)

        controls = QHBoxLayout()
        self.problem_label = QLabel("Ready for your request")
        self.problem_label.setObjectName("problem")
        controls.addWidget(self.problem_label, 1)
        self.backend = QComboBox()
        self.backend.addItem("Cloud", "cloud")
        self.backend.addItem("LM Studio", "lm_studio")
        current_backend = normalize_backend(self.settings.active_backend)
        self.backend.setCurrentIndex(1 if current_backend == "lm_studio" else 0)
        self.backend.setFixedWidth(105)
        controls.addWidget(self.backend)
        self.ai_settings = QPushButton("⚙  AI Settings")
        self.ai_settings.setFixedWidth(118)
        self.ai_settings.setObjectName("settingsButton")
        self.ai_settings.clicked.connect(self.open_ai_settings)
        controls.addWidget(self.ai_settings)
        layout.addLayout(controls)

        self.chat = QTextBrowser()
        self.chat.setOpenExternalLinks(False)
        self.chat.setObjectName("chat")
        layout.addWidget(self.chat, 1)

        composer = QHBoxLayout()
        self.input = QPlainTextEdit()
        self.input.setPlaceholderText("Describe your IT problem…  e.g. “My memory is overloaded” or “My subscription disappeared”")
        self.input.setFixedHeight(58)
        self.input.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        composer.addWidget(self.input, 1)
        self.send = QPushButton("Send  ➤")
        self.send.setFixedSize(105, 58)
        self.send.setObjectName("sendButton")
        self.send.clicked.connect(self.start_agent)
        composer.addWidget(self.send)
        layout.addLayout(composer)
        self.setCentralWidget(root)

    def _style(self):
        self.setStyleSheet(
            """
        QWidget { background: #f5f7fb; color: #172033; font-family: "Segoe UI"; font-size: 12px; }
        #title { color: #172033; font-size: 20px; font-weight: 700; padding: 0; }
        #subtitle { color: #667085; font-size: 11px; padding-top: 1px; }
        #closeButton { background: transparent; border: none; color: #667085; font-size: 22px; border-radius: 8px; }
        #closeButton:hover { background: #e9edf5; color: #172033; }
        #problem { background: #ffffff; border: 1px solid #d7ddea; border-radius: 10px; padding: 8px 12px; color: #475467; font-size: 12px; }
        QComboBox { background: #ffffff; border: 1px solid #d7ddea; border-radius: 9px; padding: 7px 10px; color: #344054; }
        QComboBox:hover { border-color: #98a2b3; }
        QComboBox::drop-down { border: none; width: 24px; }
        #settingsButton { background: #ffffff; border: 1px solid #d7ddea; border-radius: 9px; padding: 7px 10px; color: #344054; font-weight: 600; }
        #settingsButton:hover { background: #eef2f8; border-color: #98a2b3; }
        #chat { background: #ffffff; border: 1px solid #d7ddea; border-radius: 12px; padding: 12px; selection-background-color: #dbeafe; }
        QPlainTextEdit { background: #ffffff; border: 1px solid #d7ddea; border-radius: 11px; padding: 10px 12px; color: #172033; }
        QPlainTextEdit:focus { border: 1px solid #7c8db5; }
        #sendButton { background: #172033; border: 1px solid #172033; border-radius: 11px; color: #ffffff; font-size: 13px; font-weight: 700; }
        #sendButton:hover { background: #2b3852; }
        #sendButton:disabled { background: #aab2c0; border-color: #aab2c0; }
        """
        )

    def _append(self, who: str, message: str):
        safe = html.escape(message).replace("\n", "<br>")
        self.chat.append(f"<b>{html.escape(who)}</b><br>{safe}<br>")
        self.chat.verticalScrollBar().setValue(self.chat.verticalScrollBar().maximum())

    @Slot()
    def start_agent(self):
        if self.worker and self.worker.isRunning():
            return
        problem = self.input.toPlainText().strip()
        if not problem:
            return

        self.problem_label.setText(f"Problem: {problem[:55]}" + ("…" if len(problem) > 55 else ""))
        self._append("You", problem)
        self._append("Agent", "Working…")
        self.send.setEnabled(False)
        self.backend.setEnabled(False)
        self.ai_settings.setEnabled(False)
        self.worker = AgentWorker(self.service, problem, self.backend.currentData())
        self.worker.event_signal.connect(self.on_event)
        self.worker.approval_signal.connect(self.on_approval)
        self.worker.user_decision_signal.connect(self.on_user_decision)
        self.worker.finished_signal.connect(self.on_finished)
        self.worker.start()
        self.input.clear()

    @Slot(object)
    def on_event(self, event: AgentEvent):
        labels = {
            "classification": "Agent",
            "status": "Agent",
            "model": "Agent",
            "tool": "Tool",
            "tool_result": "Result",
            "resolved": "Agent",
            "ticket": "Ticket",
            "unsupported": "Agent",
            "general_chat": "Agent",
            "ask": "Agent",
            "email": "Email",
            "email_error": "Email Error",
            "internal_error": "Error",
        }
        self._append(labels.get(event.kind, "Agent"), event.message)

        if event.kind == "resolved" and event.payload and event.payload.get("report"):
            self._append("JSON report", json.dumps(event.payload["report"], indent=2))
        elif event.kind == "ticket" and event.payload:
            self._append("Ticket", f"Saved: {event.payload.get('path', '')}")
        elif event.kind == "unsupported" and event.payload:
            self._append("Ticket", f"Saved: {event.payload.get('path', '')}")
        elif event.kind == "internal_error":
            QMessageBox.warning(self, "Agent error", event.message)

    @Slot(object, str, str)
    def on_approval(self, action: str, message: str, reason: str):
        dialog = DecisionDialog(self, action, message, reason)
        dialog.exec()
        if self.worker:
            self.worker.respond_to_approval(dialog.choice)

    @Slot(object, str, str)
    def on_user_decision(self, action: str, message: str, reason: str):
        if action == "EMAIL_RECIPIENT":
            from PySide6.QtWidgets import QInputDialog
            while True:
                recipient, ok = QInputDialog.getText(
                    self,
                    "Support Team Email",
                    "Enter the support team's recipient email:",
                )
                recipient = recipient.strip()
                if not ok:
                    choice = ApprovalResponse("no", "")
                    break
                if is_valid_email(recipient):
                    choice = ApprovalResponse("idea", recipient)
                    break
                QMessageBox.warning(self, "Support Team Email", "Enter a valid recipient email address.")
            if self.worker:
                self.worker.respond_to_approval(choice)
            return

        dialog = DecisionDialog(self, action, message, reason)
        dialog.exec()
        if self.worker:
            self.worker.respond_to_approval(dialog.choice)

    @Slot()
    def on_finished(self):
        # Completing one request never closes the agent. The window remains alive
        # until the user explicitly closes it, and a new request can be submitted.
        self.send.setEnabled(True)
        self.backend.setEnabled(True)
        self.ai_settings.setEnabled(True)
        self.settings = load_settings()
        self.worker = None
        self.input.setFocus()
        self.problem_label.setText("Ready for your request")

    @Slot()
    def open_ai_settings(self):
        if self.worker and self.worker.isRunning():
            return
        dialog = AISettingsDialog(self, self.backend.currentData())
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.settings = load_settings()
            current_backend = normalize_backend(self.settings.active_backend)
            self.backend.setCurrentIndex(1 if current_backend == "lm_studio" else 0)

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.respond_to_approval(ApprovalResponse("no", "Window closed; do not execute the proposed change."))
            self.worker.wait(1500)
        event.accept()
