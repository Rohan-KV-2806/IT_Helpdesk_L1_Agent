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
    finished_signal = Signal()

    def __init__(self, service: AgentService, problem: str, backend: str):
        super().__init__()
        self.service = service
        self.problem = problem
        self.backend = backend
        self._approval: ApprovalBridge | None = None

    def run(self):
        try:
            self.service.run(self.problem, self.backend, self.event_signal.emit, self._request_approval)
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

    def respond_to_approval(self, response: ApprovalResponse):
        if self._approval:
            self._approval.respond(response)


class DecisionDialog(QDialog):
    def __init__(self, parent, action: str, message: str, reason: str):
        super().__init__(parent)
        self.is_resolution_confirmation = action == "CONFIRM_RESOLUTION"
        self.setWindowTitle("Problem Solved?") if self.is_resolution_confirmation else self.setWindowTitle("L1 Fix Decision")
        self.setModal(True)
        self.setMinimumWidth(520)
        self.choice = ApprovalResponse("no", "")

        layout = QVBoxLayout(self)
        if self.is_resolution_confirmation:
            title = QLabel("Is your problem solved?")
            body_text = f"{message}\n\nReason: {reason}\n\nPlease confirm whether the original problem is actually gone."
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
        self.setFixedSize(620, 430)
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
        title = QLabel("L1 Agent")
        title.setObjectName("title")
        title_row.addWidget(title)
        title_row.addStretch()
        close_btn = QPushButton("×")
        close_btn.setObjectName("closeButton")
        close_btn.setFixedSize(38, 34)
        close_btn.clicked.connect(self.close)
        title_row.addWidget(close_btn)
        layout.addLayout(title_row)

        controls = QHBoxLayout()
        self.problem_label = QLabel("Problem: waiting for request")
        self.problem_label.setObjectName("problem")
        controls.addWidget(self.problem_label, 1)
        self.backend = QComboBox()
        self.backend.addItems(["cloud", "local"])
        self.backend.setCurrentText("cloud")
        self.backend.setFixedWidth(86)
        controls.addWidget(self.backend)
        layout.addLayout(controls)

        self.chat = QTextBrowser()
        self.chat.setOpenExternalLinks(False)
        self.chat.setObjectName("chat")
        layout.addWidget(self.chat, 1)

        composer = QHBoxLayout()
        self.input = QPlainTextEdit()
        self.input.setPlaceholderText("Type here")
        self.input.setFixedHeight(43)
        self.input.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        composer.addWidget(self.input, 1)
        self.send = QPushButton("send")
        self.send.setFixedSize(80, 43)
        self.send.clicked.connect(self.start_agent)
        composer.addWidget(self.send)
        layout.addLayout(composer)
        self.setCentralWidget(root)

    def _style(self):
        self.setStyleSheet(
            """
        QWidget { background: #fbfaf8; color: #262626; font-family: "Segoe UI"; font-size: 12px; }
        #title { background: #ffffff; border: 1px solid #1f1f1f; padding: 5px 9px; font-size: 16px; font-weight: 650; }
        #closeButton, #send { background: #ffffff; border: 1px solid #1f1f1f; color: #1f1f1f; font-size: 14px; }
        #closeButton:hover, #send:hover { background: #f0efec; }
        #problem { background: #ffffff; border: 1px solid #555555; padding: 6px 10px; font-size: 13px; }
        QComboBox { background: #ffffff; border: 1px solid #555555; padding: 6px 8px; }
        QComboBox::drop-down { border: none; width: 22px; }
        #chat { background: #ffffff; border: 1px solid #555555; padding: 8px; }
        QPlainTextEdit { background: #ffffff; border: 1px solid #555555; padding: 8px 10px; }
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
        self.worker = AgentWorker(self.service, problem, self.backend.currentText())
        self.worker.event_signal.connect(self.on_event)
        self.worker.approval_signal.connect(self.on_approval)
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

    @Slot()
    def on_finished(self):
        self.send.setEnabled(True)
        self.backend.setEnabled(True)
        self.worker = None
        self.input.setFocus()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.respond_to_approval(ApprovalResponse("no", "Window closed; do not execute the proposed change."))
            self.worker.wait(1500)
        event.accept()
