import calendar
from datetime import datetime
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Label, Button
from messages import CalendarItemSelected

class CalendarItemCard(Horizontal):
    def __init__(self, item_data: dict) -> None:
        i_type = item_data.get("item_type", "unknown")
        super().__init__(classes=f"calendar-card calendar-card-{i_type}")
        self.item_data = item_data

    def _get_val(self, *keys):
        for k in keys:
            if k in self.item_data and self.item_data[k] is not None:
                return self.item_data[k]
        return None

    def compose(self) -> ComposeResult:
        i_type = self.item_data.get("item_type", "unknown")
        icon = "📺" 
        if i_type == "movie": 
            icon = "🎞️"
            
        with Vertical(classes="calendar-card-icon"):
            yield Label(icon)
            
        with Vertical(classes="calendar-card-content"):
            title = self._get_val("title", "name", "show_title", "showTitle", "movie_title", "original_title") or "Unknown"
            show_title = self._get_val("show_title", "showTitle")
            
            # Use Show Title as primary title for TV items if available
            display_title = title
            if i_type in ("episode", "season", "show") and show_title:
                display_title = show_title
            
            yield Label(display_title, classes="calendar-card-title")
            
            meta = []
            if i_type == "episode":
                s = self._get_val("season_number", "seasonNumber", "season")
                e = self._get_val("episode_number", "episodeNumber", "episode")
                if s is not None and e is not None:
                    meta.append(f"Season {s}, Episode {e}")
                elif s is not None:
                    meta.append(f"Season {s}")
                elif e is not None:
                    meta.append(f"Episode {e}")
                
                # For episodes, if we used show title above, put episode title in meta
                if show_title and title and title != show_title and title != "Unknown":
                    meta.append(f'"{title}"')
            elif i_type == "season":
                s = self._get_val("season_number", "seasonNumber", "season")
                if s is not None:
                    meta.append(f"Season {s}")
                
            yield Label(" • ".join(meta), classes="calendar-card-meta")

class CalendarHeader(Horizontal):
    def __init__(self, year: int, month: int):
        super().__init__(id="calendar-header-container")
        self.year = year
        self.month = month

    def compose(self) -> ComposeResult:
        yield Button("<<", id="btn-prev-year-main")
        yield Button("<", id="btn-prev-month-main")
        yield Label(f"{calendar.month_name[self.month]} {self.year}", id="calendar-month-label")
        yield Button(">", id="btn-next-month-main")
        yield Button(">>", id="btn-next-year-main")
