from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import RichLog, Input, Button, Checkbox
from textual.reactive import reactive
from rich.markup import escape
from typing import List

class LogsView(Vertical):
    filter_query = reactive("")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.displayed_count = 0

    def compose(self) -> ComposeResult:
        yield RichLog(id="logs-display", wrap=True, highlight=True, markup=True)
        with Horizontal(id="logs-controls"):
            yield Input(placeholder="Filter logs (use ! to exclude)...", id="logs-filter-input")
            yield Button("Refresh", id="btn-logs-refresh", variant="primary")
            yield Checkbox("Auto Refresh", id="cb-logs-auto-refresh", value=False)
            yield Button("Clear", id="btn-logs-clear", variant="error")

    def on_mount(self) -> None:
        # Sync checkbox with global state
        self.query_one("#cb-logs-auto-refresh", Checkbox).value = self.app.background_logs_enabled

    def _matches_filter(self, line: str) -> bool:
        if not self.filter_query:
            return True
        
        query = self.filter_query
        # Smart Case: case-sensitive if query has uppercase
        is_case_sensitive = any(c.isupper() for c in query)
        
        terms = query.split()
        for term in terms:
            negate = term.startswith("!")
            search_term = term[1:] if negate else term
            
            if not search_term:
                continue

            if is_case_sensitive:
                found = search_term in line
            else:
                found = search_term.lower() in line.lower()
            
            if negate and found:
                return False
            if not negate and not found:
                return False
        
        return True

    def _style_line(self, line: str) -> str:
        styled_line = escape(line)
        if "|" in line:
            parts = line.split("|", 2)
            if len(parts) >= 2:
                level_part = parts[1].strip()
                color = "white"
                if "ERROR" in level_part: color = "red"
                elif "WARNING" in level_part: color = "yellow"
                elif "SUCCESS" in level_part: color = "green"
                elif "DEBUG" in level_part: color = "cyan"
                elif "PROGRAM" in level_part: color = "magenta"
                
                p0 = escape(parts[0])
                p1 = escape(parts[1])
                
                if len(parts) == 3:
                    p2 = escape(parts[2])
                    styled_line = f"{p0} | [bold {color}]{p1}[/] |{p2}"
                else:
                    styled_line = f"{p0} | [bold {color}]{p1}[/]"
        return styled_line

    def watch_filter_query(self, new_query: str) -> None:
        log_widget = self.query_one("#logs-display", RichLog)
        log_widget.clear()
        for line in self.app.global_logs:
            if "GET /api/v1/logs" in line:
                continue
            if self._matches_filter(line):
                log_widget.write(self._style_line(line))

    @on(Input.Changed, "#logs-filter-input")
    def on_filter_changed(self, event: Input.Changed) -> None:
        self.filter_query = event.value.strip()

    def process_new_global_logs(self, new_lines: List[str]):
        """Called by the main app when new lines are added to global_logs."""
        log_widget = self.query_one("#logs-display", RichLog)
        for line in new_lines:
            if "GET /api/v1/logs" in line:
                continue
            if self._matches_filter(line):
                log_widget.write(self._style_line(line))

    async def update_logs(self, refresh_all: bool = False):
        """Refreshes the view from the app's global_logs."""
        log_widget = self.query_one("#logs-display", RichLog)
        
        if refresh_all:
            log_widget.clear()
            # If global logs are empty, try to fetch immediately
            if not self.app.global_logs:
                await self.app.fetch_logs_worker()
                
            for line in self.app.global_logs:
                if "GET /api/v1/logs" in line:
                    continue
                if self._matches_filter(line):
                    log_widget.write(self._style_line(line))
        else:
            # Manual refresh also triggers a worker run to be sure
            await self.app.fetch_logs_worker()

    @on(Button.Pressed, "#btn-logs-refresh")
    async def handle_refresh(self):
        await self.update_logs(refresh_all=True)

    @on(Button.Pressed, "#btn-logs-clear")
    def handle_clear(self):
        self.query_one("#logs-display", RichLog).clear()
        self.app.global_logs = []

    @on(Checkbox.Changed, "#cb-logs-auto-refresh")
    def handle_auto_refresh(self, event: Checkbox.Changed):
        self.app.background_logs_enabled = event.value

