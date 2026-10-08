from __future__ import annotations

from PySide6.QtCore import QThread, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..llm.provider import ModelProvider
from ..settings import ProviderSettings, load_settings, normalize_backend, save_settings


class _ModelListWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, endpoint: str, api_key: str):
        super().__init__()
        self.endpoint = endpoint
        self.api_key = api_key

    def run(self):
        try:
            models = ModelProvider.list_models_for_config(self.endpoint, self.api_key)
            self.succeeded.emit(models)
        except Exception as exc:
            self.failed.emit(str(exc))


class ProviderTab(QWidget):
    models_loaded = Signal(str, object)

    def __init__(self, label: str, settings: ProviderSettings):
        super().__init__()
        self.label = label
        self._worker: _ModelListWorker | None = None
        self._build(settings)

    def _build(self, settings: ProviderSettings):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        form = QFormLayout()
        self.endpoint = QLineEdit(settings.endpoint)
        self.endpoint.setPlaceholderText("https://provider.example/v1")
        form.addRow("Endpoint", self.endpoint)

        self.api_key = QLineEdit(settings.api_key)
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText("Optional for LM Studio")
        form.addRow("API key", self.api_key)

        model_row = QHBoxLayout()
        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.setCurrentText(settings.model)
        self.model.setPlaceholderText("Select or type a model ID")
        model_row.addWidget(self.model, 1)
        self.refresh = QPushButton("Refresh models")
        self.refresh.clicked.connect(self.refresh_models)
        model_row.addWidget(self.refresh)
        form.addRow("Model", model_row)
        root.addLayout(form)

        self.status = QLabel("Models are loaded from the endpoint when you press Refresh models.")
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        root.addStretch()

    def values(self) -> ProviderSettings:
        return ProviderSettings(
            endpoint=self.endpoint.text().strip(),
            api_key=self.api_key.text().strip(),
            model=self.model.currentText().strip(),
        )

    def refresh_models(self):
        endpoint = self.endpoint.text().strip()
        if not endpoint:
            self.status.setText("Enter an endpoint first.")
            return
        self.refresh.setEnabled(False)
        self.status.setText(f"Connecting to {endpoint} …")
        self._worker = _ModelListWorker(endpoint, self.api_key.text().strip())
        self._worker.succeeded.connect(self._models_ok)
        self._worker.failed.connect(self._models_failed)
        self._worker.finished.connect(self._worker_finished)
        self._worker.start()

    @Slot(object)
    def _models_ok(self, models):
        current = self.model.currentText().strip()
        self.model.clear()
        self.model.addItems([str(x) for x in models])
        if current:
            index = self.model.findText(current)
            if index >= 0:
                self.model.setCurrentIndex(index)
            else:
                self.model.setCurrentText(current)
        self.status.setText(f"Loaded {len(models)} model(s).")
        self.models_loaded.emit(self.label, models)

    @Slot(str)
    def _models_failed(self, message: str):
        self.status.setText(f"Model list failed: {message}")

    @Slot()
    def _worker_finished(self):
        self.refresh.setEnabled(True)
        self._worker = None


class AISettingsDialog(QDialog):
    def __init__(self, parent=None, initial_backend: str | None = None):
        super().__init__(parent)
        self.setWindowTitle("AI Settings")
        self.setModal(True)
        self.setMinimumSize(690, 480)
        self.settings = load_settings()
        self.initial_backend = initial_backend
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        intro = QLabel(
            "Configure the AI backends used by the helpdesk agent. Both providers use an OpenAI-compatible API. "
            "LM Studio stays completely local: it serves your selected local model and this app only sends requests to its endpoint."
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        self.tabs = QTabWidget()
        self.cloud_tab = ProviderTab("Cloud", self.settings.cloud)
        self.lm_tab = ProviderTab("LM Studio", self.settings.lm_studio)
        self.tabs.addTab(self.cloud_tab, "Cloud")
        self.tabs.addTab(self.lm_tab, "LM Studio")
        self.email_tab = self._build_email_tab(self.settings.email)
        self.tabs.addTab(self.email_tab, "Support Email")
        root.addWidget(self.tabs, 1)

        advanced = QGroupBox("Generation")
        advanced_form = QFormLayout(advanced)
        generation = self.settings.generation
        self.temperature = QDoubleSpinBox()
        self.temperature.setRange(0.0, 2.0)
        self.temperature.setSingleStep(0.1)
        self.temperature.setDecimals(2)
        self.temperature.setValue(generation.temperature)
        advanced_form.addRow("Temperature", self.temperature)

        self.top_p = QDoubleSpinBox()
        self.top_p.setRange(0.0, 1.0)
        self.top_p.setSingleStep(0.05)
        self.top_p.setDecimals(2)
        self.top_p.setValue(generation.top_p)
        advanced_form.addRow("Top-p", self.top_p)

        self.max_tokens = QSpinBox()
        self.max_tokens.setRange(256, 32768)
        self.max_tokens.setValue(generation.max_tokens)
        advanced_form.addRow("Max output tokens", self.max_tokens)

        self.max_steps = QSpinBox()
        self.max_steps.setRange(4, 100)
        self.max_steps.setValue(generation.max_agent_steps)
        advanced_form.addRow("Max agent steps", self.max_steps)
        root.addWidget(advanced)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Cancel")
        save = QPushButton("Save")
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self._save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        root.addLayout(buttons)

        current = normalize_backend(self.initial_backend or self.settings.active_backend)
        self.active_backend = QComboBox()
        self.active_backend.addItem("Cloud", "cloud")
        self.active_backend.addItem("LM Studio", "lm_studio")
        self.active_backend.setCurrentIndex(1 if current == "lm_studio" else 0)
        # Insert the default-backend selector above the provider tabs.
        root.insertWidget(1, QLabel("Default backend"))
        root.insertWidget(2, self.active_backend)

    def _build_email_tab(self, email_settings):
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        helper = QLabel(
            "These credentials are used only when an L1 ticket is raised. "
            "For Gmail, use your full email address and a Google App Password rather than your normal Google password."
        )
        helper.setWordWrap(True)
        root.addWidget(helper)

        form = QFormLayout()
        self.sender_email = QLineEdit(email_settings.sender_email)
        self.sender_email.setPlaceholderText("your-support-account@gmail.com")
        form.addRow("Sender email", self.sender_email)

        self.smtp_password = QLineEdit(email_settings.smtp_password)
        self.smtp_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.smtp_password.setPlaceholderText("Google App Password / SMTP password")
        form.addRow("Email password", self.smtp_password)

        self.smtp_host = QLineEdit(email_settings.smtp_host)
        form.addRow("SMTP host", self.smtp_host)

        self.smtp_port = QSpinBox()
        self.smtp_port.setRange(1, 65535)
        self.smtp_port.setValue(int(email_settings.smtp_port))
        form.addRow("SMTP port", self.smtp_port)

        self.smtp_security = QComboBox()
        self.smtp_security.addItem("SSL", "ssl")
        self.smtp_security.addItem("STARTTLS", "starttls")
        security_index = 1 if str(email_settings.security).lower() == "starttls" else 0
        self.smtp_security.setCurrentIndex(security_index)
        form.addRow("Security", self.smtp_security)
        root.addLayout(form)

        note = QLabel("Default Gmail SMTP: smtp.gmail.com / 465 / SSL")
        note.setStyleSheet("color: #555555;")
        root.addWidget(note)
        root.addStretch()
        return page

    def _email_values(self):
        from ..settings import EmailSettings
        return EmailSettings(
            sender_email=self.sender_email.text().strip(),
            smtp_password=self.smtp_password.text().strip(),
            smtp_host=self.smtp_host.text().strip(),
            smtp_port=int(self.smtp_port.value()),
            security=str(self.smtp_security.currentData()),
        )

    def _save(self):
        cloud = self.cloud_tab.values()
        lm = self.lm_tab.values()
        if not cloud.endpoint:
            QMessageBox.warning(self, "AI Settings", "Cloud endpoint cannot be empty.")
            return
        if not lm.endpoint:
            QMessageBox.warning(self, "AI Settings", "LM Studio endpoint cannot be empty.")
            return

        email = self._email_values()
        if email.sender_email and "@" not in email.sender_email:
            QMessageBox.warning(self, "AI Settings", "Sender email does not look valid.")
            return
        if not email.smtp_host:
            QMessageBox.warning(self, "AI Settings", "SMTP host cannot be empty.")
            return
        self.settings.cloud = cloud
        self.settings.lm_studio = lm
        self.settings.email = email
        self.settings.active_backend = self.active_backend.currentData()
        generation = self.settings.generation
        generation.temperature = self.temperature.value()
        generation.top_p = self.top_p.value()
        generation.max_tokens = self.max_tokens.value()
        generation.max_agent_steps = self.max_steps.value()

        try:
            save_settings(self.settings)
        except OSError as exc:
            QMessageBox.critical(self, "AI Settings", f"Could not save settings: {exc}")
            return
        self.accept()
