from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Input, Label


class InputModal(ModalScreen[str | None]):

    BINDINGS = [Binding("escape", "cancel", "取消", show=False)]

    class Submitted(Message):
        def __init__(self, value: str) -> None:
            super().__init__()
            self.value = value

    def __init__(
        self,
        title: str,
        placeholder: str = "",
        validator: callable | None = None,
    ) -> None:
        super().__init__()
        self._title = title
        self._placeholder = placeholder
        self._validator = validator

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-container"):
            yield Label(self._title, id="modal-title")
            yield Input(placeholder=self._placeholder, id="modal-input")
            yield Label("", id="modal-error")

    def on_mount(self) -> None:
        self.query_one("#modal-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        if not value:
            self.query_one("#modal-error", Label).update("输入不能为空")
            return
        if self._validator:
            err = self._validator(value)
            if err:
                self.query_one("#modal-error", Label).update(err)
                return
        self.dismiss(value)

    def action_cancel(self) -> None:
        self.dismiss(None)
