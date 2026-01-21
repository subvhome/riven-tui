from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import RichLog, Input, Button, Checkbox
from textual.reactive import reactive
from rich.markup import escape

class LogsView(Vertical):
    filter_query = reactive("")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.displayed_logs = []
        self._refresh_timer = None

    def compose(self) -> ComposeResult:
        yield RichLog(id="logs-display", wrap=True, highlight=True, markup=True)
        with Horizontal(id="logs-controls"):
            yield Input(placeholder="Filter logs (use ! to exclude)...", id="logs-filter-input")
            yield Button("Refresh", id="btn-logs-refresh", variant="primary")
            yield Checkbox("Auto Refresh", id="cb-logs-auto-refresh", value=False)
            yield Button("Clear", id="btn-logs-clear", variant="error")

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
        for line in self.displayed_logs:
            if "GET /api/v1/logs" in line:
                continue
            if self._matches_filter(line):
                log_widget.write(self._style_line(line))

    @on(Input.Changed, "#logs-filter-input")
    def on_filter_changed(self, event: Input.Changed) -> None:
        self.filter_query = event.value.strip()

    async def update_logs(self, refresh_all: bool = False):
        riven_key = self.app.settings.get("riven_key")
        logs, error = await self.app.api.get_direct_logs(riven_key)
        
        if error:
            self.app.notify(f"Error fetching logs: {error}", severity="error")
            return

        log_widget = self.query_one("#logs-display", RichLog)
        
        if refresh_all:
            log_widget.clear()
            self.displayed_logs = []
            # Apply display limit on initial load
            limit = self.app.settings.get("log_display_limit", 50)
            if len(logs) > limit:
                logs = logs[-limit:]

        # Find new logs
        new_lines = []
        if not self.displayed_logs:
            new_lines = logs
        else:
            last_line = self.displayed_logs[-1]
            try:
                idx = -1
                for i in range(len(logs) - 1, -1, -1):
                    if logs[i] == last_line:
                        idx = i
                        break
                
                if idx != -1:
                    new_lines = logs[idx+1:]
                else:
                    new_lines = logs
            except Exception:
                new_lines = logs

        for line in new_lines:
            if "GET /api/v1/logs" in line:
                continue
            
            self.displayed_logs.append(line)
            if self._matches_filter(line):
                log_widget.write(self._style_line(line))

    @on(Button.Pressed, "#btn-logs-refresh")
    async def handle_refresh(self):
        await self.update_logs()

    @on(Button.Pressed, "#btn-logs-clear")
    def handle_clear(self):
        self.query_one("#logs-display", RichLog).clear()
        self.displayed_logs = []

    @on(Checkbox.Changed, "#cb-logs-auto-refresh")
    def handle_auto_refresh(self, event: Checkbox.Changed):
        refresh_btn = self.query_one("#btn-logs-refresh", Button)
        if event.value:
            refresh_btn.disabled = True
            interval = self.app.settings.get("log_refresh_interval", 5.0)
            self._refresh_timer = self.set_interval(interval, self.update_logs)
        else:
            refresh_btn.disabled = False
            if self._refresh_timer:
                self._refresh_timer.stop()
                self._refresh_timer = None
