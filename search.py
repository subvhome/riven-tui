from textual import on
from textual.containers import Container, Horizontal
from textual.widgets import Label, Input
from textual.app import ComposeResult
from textual.message import Message

class SearchSubmitted(Message):
    def __init__(self, query: str) -> None:
        super().__init__()
        self.query = query

class SearchArea(Container):
    def compose(self) -> ComposeResult:
        with Horizontal(id="search-bar-row"):
            yield Label(" SEARCH: ", id="search-label") 
            yield Input(placeholder="Type here and press Enter...", id="search-input")

    @on(Input.Submitted)
    def handle_input_submitted(self, event: Input.Submitted) -> None:
        query_text = event.value.strip()
        if query_text:
            self.post_message(SearchSubmitted(query=query_text))
            self.query_one(Input).value = ""