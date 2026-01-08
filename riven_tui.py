import json
import asyncio
import math
import calendar
from datetime import datetime
from typing import List, Optional, Literal, Dict
import logging
from logging.handlers import RotatingFileHandler
import shutil
from textual import on
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, Input, ListView, ListItem, Label, Button, Log, Markdown, Select, Checkbox
from textual.containers import Container, Horizontal, Vertical
from textual.message import Message
from textual.css.query import NoMatches
from textual.screen import ModalScreen
from textual.reactive import reactive
from textual.timer import Timer
from rich.text import Text
import rich.markup
from rich.markup import escape

from api import RivenAPI
from settings_view import SettingsView
from dashboard_view import DashboardView, DashboardItemClicked, TrendingPageChanged
from advanced_view import AdvancedView
import subprocess

NOTIFICATION_CLEAR_DELAY = 10.0 # Seconds

class ScrapeLogScreen(ModalScreen):
    def __init__(self, name: str | None = None, id: str | None = None, classes: str | None = None) -> None:
        super().__init__(name=name, id=id, classes=f"{classes or ''} centered-modal-screen".strip())

    def compose(self) -> ComposeResult:
        with Vertical(id="scrape-log-container", classes="modal-popup"):
            yield Static("Discovering streams...", id="scrape-log-title")
            yield Log(id="scrape-log", highlight=True)
            yield Button("Close", id="btn-close-scrape-log", variant="error")

    def on_mount(self) -> None:
        self.query_one(Log).write_line("Starting stream discovery...")

    @on(Button.Pressed, "#btn-close-scrape-log")
    def on_close_button(self, event: Button.Pressed):
        self.app.pop_screen()

class StreamSelectionScreen(ModalScreen[str]):
    def __init__(self, streams: List[dict], name: str | None = None, id: str | None = None, classes: str | None = None) -> None:
        super().__init__(name=name, id=id, classes=f"{classes or ''} centered-modal-screen".strip())
        self.streams = streams

    def compose(self) -> ComposeResult:
        with Vertical(id="stream-selection-container", classes="modal-popup"):
            yield Static("Select a Stream to Scrape", id="stream-selection-title")
            yield ListView(id="stream-list")
            yield Button("Cancel", id="btn-cancel-stream-selection", variant="error")

    def on_mount(self) -> None:
        lv = self.query_one(ListView)
        for stream in self.streams:
            raw_title = escape(stream.get('raw_title', 'Unknown Stream'))
            resolution = stream.get('resolution', 'N/A')
            rank = stream.get('rank', 'N/A')
            
            label_text = f"{raw_title} (Res: {resolution}, Rank: {rank})"

            if stream.get('failed'):
                label_text = f"[s]{label_text}[/s]"
            
            label = Label(Text.from_markup(label_text))
            list_item = ListItem(label)
            list_item.stream_data = stream

            if stream.get('failed'):
                list_item.disabled = True
            
            lv.append(list_item)


    @on(ListView.Selected)
    def on_stream_selected(self, event: ListView.Selected):
        infohash = event.item.stream_data.get("infohash")
        if infohash:
            magnet_link = f"magnet:?xt=urn:btih:{infohash}"
            self.dismiss(magnet_link)
        else:
            self.app.notify("No infohash found for the selected stream.", severity="error")
            self.dismiss(None)

    @on(Button.Pressed, "#btn-cancel-stream-selection")
    def on_cancel_button(self, event: Button.Pressed):
        self.dismiss(None)

class FileMappingScreen(ModalScreen[dict]):

    def __init__(self, files: List[dict], parsed_data: List[dict], title: str, session_id: str, name: str | None = None, id: str | None = None, classes: str | None = None) -> None:
        super().__init__(name=name, id=id, classes=f"{classes or ''} centered-modal-screen".strip())
        self.files = files
        self.parsed_map = {p['raw_title']: p for p in parsed_data if 'raw_title' in p}
        self.title = title
        self.session_id = session_id

    def compose(self) -> ComposeResult:
        with Vertical(id="file-mapping-container", classes="modal-container modal-popup"):
            yield Static(f"Map Files for: [bold]{self.title}[/bold]", id="file-mapping-title")
            
            with Vertical(id="file-mapping-list", classes="scrollable-container"):
                for i, file_info in enumerate(self.files):
                    with Horizontal(classes="file-mapping-item"):
                        yield Label(file_info.get("filename", "Unknown file"), classes="filename-label")
                        yield Input(
                            placeholder="S", 
                            id=f"season-input-{i}", 
                            classes="season-episode-input"
                        )
                        yield Input(
                            placeholder="E", 
                            id=f"episode-input-{i}", 
                            classes="season-episode-input"
                        )
            
            with Horizontal(id="file-mapping-buttons", classes="button-bar"):
                yield Button("Confirm", id="btn-confirm-mapping", variant="success")
                yield Button("Cancel", id="btn-cancel-mapping", variant="primary")
                yield Button("Abort Session", id="btn-abort-session", variant="error")

    def on_mount(self) -> None:
        for i, item_container in enumerate(self.query(".file-mapping-item")):
            item_container.file_data = self.files[i]
            
            file_info = self.files[i]
            filename = file_info.get("filename", "Unknown file")
            parsed = self.parsed_map.get(filename, {})

            season = ""
            if "seasons" in parsed and parsed["seasons"]:
                season = str(parsed["seasons"][0])
            
            episode = ""
            if "episodes" in parsed and parsed["episodes"]:
                episode = str(parsed["episodes"][0])

            season_input = item_container.query_one(f"#season-input-{i}", Input)
            episode_input = item_container.query_one(f"#episode-input-{i}", Input)

            season_input.value = season
            episode_input.value = episode

    @on(Button.Pressed, "#btn-confirm-mapping")
    def on_confirm_mapping(self, event: Button.Pressed) -> None: 
        mapping = {}
        has_error = False
        for i, item_container in enumerate(self.query(".file-mapping-item")):
            season_input = self.query_one(f"#season-input-{i}", Input)
            episode_input = self.query_one(f"#episode-input-{i}", Input)
            
            season_str = season_input.value.strip()
            episode_str = episode_input.value.strip()

            if not season_str and not episode_str:
                continue

            try:
                season = int(season_str)
                episode = int(episode_str)
                season_input.remove_class("input-error")
                episode_input.remove_class("input-error")
            except ValueError:
                self.notify("Invalid season or episode number. Please enter valid integers.", severity="error")
                if not season_str.isdigit():
                    season_input.add_class("input-error")
                if not episode_str.isdigit():
                    episode_input.add_class("input-error")
                has_error = True
                continue

            if str(season) not in mapping:
                mapping[str(season)] = {}
            
            file_data = item_container.file_data
            mapping[str(season)][str(episode)] = {
                "file_id": file_data.get("file_id"),
                "filename": file_data.get("filename"),
                "filesize": file_data.get("filesize"),
                "download_url": file_data.get("download_url")
            }
        
        if not has_error:
            if not mapping:
                self.notify("No files were mapped. Please map at least one file.", severity="warning")
            else:
                self.dismiss(mapping)

    @on(Button.Pressed, "#btn-cancel-mapping")
    def on_cancel_mapping(self, event: Button.Pressed) -> None: 
        self.dismiss(None)

    @on(Button.Pressed, "#btn-abort-session")
    async def on_abort_session(self, event: Button.Pressed) -> None: 
        if self.session_id:
            success, response = await self.app.api.abort_scrape_session(self.session_id, self.app.settings.get("api_key"))
            if success:
                self.app.notify("Scrape session aborted.", severity="info")
                self.dismiss(None)
            else:
                self.app.notify(f"Error aborting session: {response}", severity="error")
        else:
            self.app.notify("No session to abort.", severity="warning")
            self.dismiss(None)


class ChafaCheckScreen(ModalScreen[bool]):
    def __init__(self, name: str | None = None, id: str | None = None, classes: str | None = None) -> None:
        super().__init__(name=name, id=id, classes=f"{classes or ''} centered-modal-screen".strip())

    def compose(self) -> ComposeResult:
        with Vertical(id="chafa-check-container", classes="modal-popup"):
            yield Static("⚠️ Chafa Not Found", id="chafa-check-title")
            yield Static(
                "The [bold]chafa[/bold] command is required to display posters.\n"
                "Without it, the image feature will be disabled.\n\n"
                "To install it on Ubuntu/Debian, run:\n"
                "[bold cyan]sudo apt update && sudo apt install chafa[/bold cyan]\n\n"
                "Do you want to continue without images?",
                id="chafa-check-message"
            )
            with Horizontal(id="chafa-check-buttons"):
                yield Button("Continue", id="btn-chafa-continue", variant="primary")
                yield Button("Exit", id="btn-chafa-exit", variant="error")

    @on(Button.Pressed, "#btn-chafa-continue")
    def on_continue(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#btn-chafa-exit")
    def on_exit(self) -> None:
        self.dismiss(False)


class TitleSpinner:
    SPINNER_FRAMES = ['⣾','⣽','⣻','⢿','⡿','⣟','⣯','⣷']
    DEFAULT_INTERVAL = 0.1

    def __init__(self, app: App, base_title: str):
        self.app = app
        self.base_title = base_title
        self._spinner_task = None
        self._frame_index = 0
        self.title_widget = self.app.query_one("#header-title", Static)

    async def start(self, message: str = "Loading...", interval: float = DEFAULT_INTERVAL):
        self.stop()
        self._frame_index = 0
        self.message = message
        self._spinner_task = self.app.set_interval(
            interval, self._update_spinner, name="title_spinner_task"
        )
        self.title_widget.update(f"{self.base_title} - {self.message} {self.SPINNER_FRAMES[self._frame_index]}")

    def stop(self):
        if self._spinner_task:
            self._spinner_task.stop()
            self._spinner_task = None
        self.title_widget.update(self.base_title)

    def _update_spinner(self):
        self._frame_index = (self._frame_index + 1) % len(self.SPINNER_FRAMES)
        self.title_widget.update(f"{self.base_title} - {self.message} {self.SPINNER_FRAMES[self._frame_index]}")


class SearchSubmitted(Message):
    def __init__(self, query: str) -> None:
        super().__init__()
        self.query = query

class RefreshPoster(Message):
    pass

class SearchArea(Container):
    def compose(self) -> ComposeResult:
        with Horizontal(id="search-bar-row"):
            yield Label(" SEARCH: ", id="search-label") 
            yield Input(placeholder="Type title and press Enter...", id="search-input")

    @on(Input.Submitted)
    def handle_search_submitted(self, event: Input.Submitted) -> None: 
        if event.value.strip():
            self.app.post_message(SearchSubmitted(query=event.value.strip()))

class SearchResultItem(ListItem):
    def __init__(self, item_data: dict) -> None:
        
        m_type_raw = item_data.get('media_type', 'unknown')
        prefix_text = ""
        if m_type_raw == 'movie':
            prefix_text = "\U0001F3AC" # 🎬
        elif m_type_raw == 'tv':
            prefix_text = "\U0001F4FA" # 📺
        
        title_text = item_data.get('title') or item_data.get('name') or 'Unknown'
        release_date = item_data.get('release_date') or item_data.get('first_air_date')
        year = f" ({release_date[:4]})" if release_date and len(release_date) >= 4 else ""
        self.display_title = f"{prefix_text} {title_text}{year}"
        self.item_data = item_data

        super().__init__(classes="sidebar-item-layout")

    def compose(self) -> ComposeResult:
        yield Label(self.display_title)

class PageChanged(Message):
    def __init__(self, page: int) -> None:
        self.page = page
        super().__init__()

class PaginationControl(Horizontal):
    def __init__(self, page: int, total_pages: int) -> None:
        super().__init__(id="pagination-container")
        self.page = page
        self.total_pages = total_pages

    def compose(self) -> ComposeResult:
        yield Button("<", id="btn-prev-page", disabled=self.page <= 1)
        yield Label(f"Page {self.page} of {self.total_pages}", classes="pagination-label")
        yield Button(">", id="btn-next-page", disabled=self.page >= self.total_pages)

class MonthChanged(Message):
    def __init__(self, year: int, month: int) -> None:
        self.year = year
        self.month = month
        super().__init__()

class FilterPill(Static):
    class Changed(Message):
        def __init__(self, filter_type: str, value: bool) -> None:
            self.filter_type = filter_type
            self.value = value
            super().__init__()

    def __init__(self, label: str, value: bool, filter_type: str):
        super().__init__(label, id=filter_type, classes="filter-pill")
        self.filter_type = filter_type
        self.value = value
        self.add_class(f"pill-{filter_type}")
        if value:
            self.add_class("-on")

    def on_click(self) -> None:
        self.value = not self.value
        self.set_class(self.value, "-on")
        self.post_message(self.Changed(self.filter_type, self.value))

class CalendarItemCard(Horizontal):
    def __init__(self, item_data: dict) -> None:
        i_type = item_data.get("item_type", "unknown")
        super().__init__(classes=f"calendar-card calendar-card-{i_type}")
        self.item_data = item_data

    def compose(self) -> ComposeResult:
        i_type = self.item_data.get("item_type", "unknown")
        icon = "📺" 
        color = "#3498DB" # Default blue
        if i_type == "movie": 
            icon = "🎞️"
            color = "#E67E22"
        elif i_type == "season":
            color = "#2ECC71"
        elif i_type == "show":
            color = "#9B59B6"
        
        yield Label(f"[{color}]{icon}[/]", classes="calendar-card-icon")
        with Vertical(classes="calendar-card-content"):
            title = self.item_data.get("show_title") or self.item_data.get("title") or "Unknown"
            yield Label(title, classes="calendar-card-title")
            
            season = self.item_data.get("season")
            episode = self.item_data.get("episode")
            meta = ""
            if season is not None:
                meta = f"Season {season}"
                if episode is not None:
                    meta += f" , Episode {episode}"
            if meta:
                yield Label(meta, classes="calendar-card-meta")

class CalendarHeader(Horizontal):
    def __init__(self, year: int, month: int) -> None:
        super().__init__(id="calendar-header-container")
        self.year = year
        self.month = month

    def compose(self) -> ComposeResult:
        month_name = calendar.month_name[self.month]
        yield Button("<", id="btn-prev-month")
        yield Label(f"{month_name} {self.year}", id="calendar-month-label")
        yield Button(">", id="btn-next-month")

    @on(Button.Pressed, "#btn-prev-month")
    def on_prev(self):
        new_month = self.month - 1
        new_year = self.year
        if new_month < 1:
            new_month = 12
            new_year -= 1
        self.post_message(MonthChanged(new_year, new_month))

    @on(Button.Pressed, "#btn-next-month")
    def on_next(self):
        new_month = self.month + 1
        new_year = self.year
        if new_month > 12:
            new_month = 1
            new_year += 1
        self.post_message(MonthChanged(new_year, new_month))

class Sidebar(Container):
    def compose(self) -> ComposeResult:
        yield Static("Main Menu", id="sidebar-title")
        with Vertical(id="sidebar-list-container"):
            yield ListView(id="sidebar-list")
        
        with Vertical(id="sidebar-filters-container"):
            with Vertical(classes="filter-scroll-area"):
                yield Label("Search:")
                yield Input(placeholder="Search library...", id="lib-filter-search")
                
                yield Label("Type:")
                yield Select([
                    ("All", None), 
                    ("Movie", "movie"), 
                    ("TV Show", "show"),
                    ("Anime", "anime")
                ], prompt="Type", id="lib-filter-type", allow_blank=False, value=None)
                
                yield Label("States:")
                yield Select([
                    ("All", None),
                    ("Unknown", "Unknown"),
                    ("Unreleased", "Unreleased"),
                    ("Ongoing", "Ongoing"),
                    ("Requested", "Requested"),
                    ("Indexed", "Indexed"),
                    ("Scraped", "Scraped"),
                    ("Downloaded", "Downloaded"),
                    ("Symlinked", "Symlinked"),
                    ("Completed", "Completed"),
                    ("Partially Completed", "PartiallyCompleted"),
                    ("Failed", "Failed"),
                    ("Paused", "Paused")
                ], prompt="States", id="lib-filter-states", allow_blank=False, value=None)

                yield Label("Sort:")
                yield Select([
                    ("Date Desc", "date_desc"), 
                    ("Date Asc", "date_asc"), 
                    ("Title Asc", "title_asc"), 
                    ("Title Desc", "title_desc")
                ], prompt="Sort", id="lib-filter-sort", allow_blank=False, value="date_desc")
                
                yield Label("Limit:")
                yield Select([("5", 5), ("10", 10), ("20", 20), ("50", 50)], prompt="Limit", id="lib-filter-limit", allow_blank=False, value=20)
                
                yield Label("Page:")
                yield Input("1", placeholder="Page", id="lib-filter-page")

                with Horizontal(classes="checkbox-row"):
                    yield Checkbox("Count Only", id="lib-filter-count-only", value=False)

            yield Button("Apply Filters", id="btn-apply-filters", variant="success")

        with Vertical(id="sidebar-calendar-container"):
            yield Static("MONTHLY STATS", classes="sidebar-subtitle")
            yield Static("", id="calendar-sidebar-stats")
            yield Static("_" * 38, classes="sidebar-separator")
            
            yield Static("JUMP TO DATE", classes="sidebar-subtitle")
            with Horizontal(classes="calendar-jumper-row"):
                yield Button("<", id="btn-prev-year-sidebar", classes="jumper-btn")
                yield Label("2026", id="label-year-sidebar", classes="jumper-label")
                yield Button(">", id="btn-next-year-sidebar", classes="jumper-btn")
            
            with Horizontal(classes="calendar-jumper-row"):
                yield Button("<", id="btn-prev-month-sidebar", classes="jumper-btn")
                yield Label("January", id="label-month-sidebar", classes="jumper-label")
                yield Button(">", id="btn-next-month-sidebar", classes="jumper-btn")
            
            yield Static("_" * 38, classes="sidebar-separator")
            with Vertical(id="calendar-grid-container"):
                pass

    def on_mount(self) -> None:
        self.show_categories()

    def show_categories(self) -> None:
        self.query_one("#sidebar-title", Static).update("Main Menu")
        self.query_one("#sidebar-list-container").display = True
        self.query_one("#sidebar-filters-container").display = False
        
        items = [ListItem(Label(n), name=n) for n in ["Logs", "Settings"]]
        lv = self.query_one(ListView)
        lv.clear()
        lv.extend(items)

    def show_library_filters(self) -> None:
        self.query_one("#sidebar-title", Static).update("Library Filters")
        self.query_one("#sidebar-list-container").display = False
        self.query_one("#sidebar-filters-container").display = True

    def show_calendar_summary(self) -> None:
        self.query_one("#sidebar-title", Static).update("Calendar")
        self.query_one("#sidebar-list-container").display = False
        self.query_one("#sidebar-filters-container").display = False
        self.query_one("#sidebar-calendar-container").display = True

    async def update_calendar_sidebar(self, year: int, month: int, monthly_items: List[dict], active_filters: Dict[str, bool]) -> None:
        m_count = len([i for i in monthly_items if i.get("item_type") == "movie"])
        e_count = len([i for i in monthly_items if i.get("item_type") == "episode"])
        s_count = len([i for i in monthly_items if i.get("item_type") == "show"])
        se_count = len([i for i in monthly_items if i.get("item_type") == "season"])
        
        stats_text = (
            f"Total Items: [bold]{len(monthly_items)}[/bold]\n"
            f"🎞️ Movies: {m_count}\n"
            f"📺 Episodes: {e_count}\n"
            f"📺 Shows: {s_count}\n"
            f"📺 Seasons: {se_count}"
        )
        self.query_one("#calendar-sidebar-stats").update(stats_text)

        self.query_one("#label-year-sidebar").update(str(year))
        self.query_one("#label-month-sidebar").update(calendar.month_name[month])

        grid_container = self.query_one("#calendar-grid-container")
        await grid_container.query("*").remove()
        
        header_row = Horizontal(classes="calendar-grid-row calendar-grid-header")
        await grid_container.mount(header_row)
        for day_name in ["S", "M", "T", "W", "T", "F", "S"]:
            await header_row.mount(Label(day_name, classes="grid-cell grid-header-cell"))

        cal_matrix = calendar.monthcalendar(year, month)
        
        content_days = {i["_dt"].day for i in monthly_items if "_dt" in i}

        for week in cal_matrix:
            week_row = Horizontal(classes="calendar-grid-row")
            await grid_container.mount(week_row)
            for day in week:
                if day == 0:
                    await week_row.mount(Label("", classes="grid-cell empty-cell"))
                else:
                    cell = DayCell(day, classes="grid-cell day-cell", id=f"grid-day-{day}")
                    if day in content_days:
                        cell.add_class("has-content")
                    await week_row.mount(cell)

    @on(Button.Pressed, ".jumper-btn")
    def on_jumper_button(self, event: Button.Pressed) -> None:
        pass

    def update_results(self, query: str, results: List[dict]) -> None:
        self.query_one("#sidebar-title", Static).update(f"Results: {query}")
        self.query_one("#sidebar-list-container").display = True
        self.query_one("#sidebar-filters-container").display = False
        
        lv = self.query_one(ListView)
        lv.clear()
        
        if not results:
            lv.extend([ListItem(Label("No Results Found"))])
        else:
            for item in results:
                lv.append(SearchResultItem(item))

    def get_filter_values(self) -> dict:
        return {
            "search": self.query_one("#lib-filter-search", Input).value,
            "type": self.query_one("#lib-filter-type", Select).value,
            "states": self.query_one("#lib-filter-states", Select).value,
            "sort": self.query_one("#lib-filter-sort", Select).value,
            "limit": self.query_one("#lib-filter-limit", Select).value,
            "page": self.query_one("#lib-filter-page", Input).value,
            "count_only": self.query_one("#lib-filter-count-only", Checkbox).value,
        }


class LibraryItemCard(Static):
    class Clicked(Message):
        def __init__(self, item_data: dict) -> None:
            self.item_data = item_data
            super().__init__()

    def __init__(self, item_data: dict, renderable: str, **kwargs) -> None:
        super().__init__(renderable, **kwargs)
        self.item_data = item_data

    def on_click(self) -> None:
        self.post_message(self.Clicked(self.item_data))

class MainContent(Vertical):
    
    item_details: Optional[dict] = None 
    tmdb_details: Optional[dict] = None 
    item_data: Optional[dict] = None 
    last_chafa_width: Optional[int] = None 

    def compose(self) -> ComposeResult:
        yield Static(id="main-content-title")
        yield Vertical(id="main-content-container")

    async def display_logs(self, logs: str):
        container = self.query_one("#main-content-container")
        await container.query("*").remove()
        await container.mount(Static(logs, id="log-content", expand=True))
        await container.mount(Button("Refresh", id="btn-refresh-logs", variant="primary"))

    async def display_json(self, data: dict):
        container = self.query_one("#main-content-container")
        await container.query("*").remove()
        
        formatted_json = json.dumps(data, indent=4)
        
        json_scroll_container = Vertical(id="json-scroll-container")
        await container.mount(json_scroll_container)
        
        await json_scroll_container.mount(Static(formatted_json, id="main-content-body"))
        await container.mount(Button("Back", id="btn-back-to-actions"))

class DayClicked(Message):
    def __init__(self, day: int) -> None:
        self.day = day
        super().__init__()

class DayCell(Static):
    def __init__(self, day: int, classes: str = "", id: str | None = None):
        super().__init__(str(day), classes=classes, id=id)
        self.day = day

    def on_click(self) -> None:
        self.post_message(DayClicked(self.day))

class RivenTUI(App):
    CSS_PATH = "riven_tui.tcss"

    base_title = reactive("Riven TUI") 
    app_state: Literal["welcome", "dashboard", "search", "library", "calendar", "settings", "advanced"] = reactive("dashboard")
    current_calendar_date = reactive(datetime.now())
    calendar_filters = reactive({"movie": True, "episode": True, "show": True, "season": True})

    def __init__(self):
        super().__init__()
        self.settings = {}
        self.previous_logs = ""
        self.chafa_available = False
        self.post_message_debounce_timer = None 
        self.file_logger = logging.getLogger("RivenTUIFileLogger")
        self.file_logger.setLevel(logging.INFO)
        handler = RotatingFileHandler('riven_tui.log', maxBytes=1024*1024, backupCount=3)
        formatter = logging.Formatter('%(asctime)s - %(message)s')
        handler.setFormatter(formatter)
        self.file_logger.addHandler(handler)
        self.spinner = None
        self._clear_notification_timer = None
        self.refresh_delay_seconds = 3.0
        self.last_library_filters = {}
        self.library_cache: List[dict] = [] 
        self.calendar_cache: List[dict] = [] 
        self.navigation_source: Literal["dashboard", "library", "search"] = "dashboard"
        self.current_trending_page = 1

    def log_message(self, message: str):
        if self.settings.get("tui_debug"):
            try:
                log_widget = self.query_one("#debug-log", Log)
                log_widget.write_line(message)
            except NoMatches:
                pass
        self.file_logger.info(message)

    def on_load(self) -> None: 
        try:
            with open("settings.json", "r") as f:
                self.settings = json.load(f)
        except Exception as e:
            self.log_message(f"Error loading settings.json: {e}")
            self.settings = {}
        
        self.chafa_available = shutil.which("chafa") is not None
        if not self.chafa_available:
            self.log_message("chafa command not found, poster feature will be disabled.")
        
    def build_url(self, config_key: str) -> str:
        cfg = self.settings.get(config_key, {})
        protocol = cfg.get("protocol", "http")
        host = cfg.get("host", "localhost")
        port = cfg.get("port")
        
        if port:
            return f"{protocol}://{host}:{port}"
        return f"{protocol}://{host}"
        
    def compose(self) -> ComposeResult:
        with Horizontal(id="header-bar"):
            yield Button("Dashboard", id="btn-header-dashboard")
            yield Button("Search", id="btn-header-search")
            yield Button("Library", id="btn-header-library")
            yield Button("Discover", id="btn-header-discover")
            yield Button("Advanced", id="btn-header-advanced")
            yield Button("Calendar", id="btn-header-calendar")
            yield Button("Settings", id="btn-header-settings")
            yield Static(self.base_title, id="header-title")

        yield SearchArea(id="search-subheader")
        
        with Container(id="workspace"):
            with Vertical(id="dashboard-wrapper"):
                yield DashboardView(id="dashboard-view")
            yield Static("Welcome to Riven TUI! Click 'Search' to begin.", id="welcome-message")
            with Horizontal(id="main-area"):
                yield Sidebar(id="sidebar")
                with Vertical(id="content-wrapper"):
                    yield MainContent(id="content-area")
                    yield Container(id="pagination-slot") 
            
            yield SettingsView(id="settings-view")
            yield AdvancedView(id="advanced-view")

        if self.settings.get("tui_debug"):
            yield Log(id="debug-log", highlight=True)

        yield Footer()

    async def on_mount(self) -> None:
        self.log_message("App mounted. Starting startup worker.")
        self.run_worker(self.perform_startup())

    async def perform_startup(self) -> None:
        if not self.chafa_available:
            if not await self.push_screen_wait(ChafaCheckScreen()):
                self.exit()
                return

        try:
            be_url = self.build_url("be_config")
            timeout = self.settings.get("request_timeout", 10.0)

            self.api = RivenAPI(be_url, timeout=timeout)
            self.log_message(f"API Initialized: BE='{be_url}'")
            self.spinner = TitleSpinner(self, self.base_title) 
            self.app_state = "dashboard" 
        except Exception as e:
            self.log_message(f"Config Error: {e}")
            self.notify(f"Config Error: {e}", severity="error")

    async def on_unmount(self) -> None:
        if hasattr(self, "api"):
            await self.api.shutdown()

    async def refresh_dashboard(self):
        if not hasattr(self, "api"):
            return
            
        dashboard_view = self.query_one(DashboardView)
        api_key = self.settings.get("api_key")
        tmdb_token = self.settings.get("tmdb_bearer_token")

        # 1. Update Stats & Health
        try:
            stats, _ = await self.api.get_stats(api_key)
            status = "Online" if stats is not None else "Offline"
            await dashboard_view.update_stats(stats, status)
            
            if stats:
                services, _ = await self.api.get_services(api_key)
                settings, _ = await self.api.get_settings(api_key)
                
                if services and settings:
                    enabled_services = []
                    # Helper to recursively find "enabled": True in settings
                    def find_enabled(obj, path=""):
                        if isinstance(obj, dict):
                            if obj.get("enabled") is True:
                                service_key = path.split(".")[-1]
                                if service_key in services:
                                    enabled_services.append(service_key)
                            for k, v in obj.items():
                                find_enabled(v, f"{path}.{k}" if path else k)

                    find_enabled(settings)
                    
                    # Ensure unique and sorted
                    enabled_services = sorted(list(set(enabled_services)))
                    await dashboard_view.update_services(services, enabled_services)
        except Exception as e:
            self.log_message(f"Dashboard Refresh Error: {e}")

        # 2. Update Recently Added
        try:
            recent_resp, _ = await self.api.get_items(api_key, limit=10, sort="date_desc")
            if recent_resp:
                await dashboard_view.update_recent(recent_resp.get("items", []))
        except Exception as e:
            self.log_message(f"Dashboard Recent Error: {e}")

        # 3. Update Trending (Paginated)
        try:
            trending_items, _ = await self.api.get_tmdb_trending(tmdb_token, page=self.current_trending_page)
            if trending_items:
                await dashboard_view.update_trending(trending_items, page=self.current_trending_page)
        except Exception as e:
            self.log_message(f"Dashboard Trending Error: {e}")

    @on(TrendingPageChanged)
    async def on_trending_page_changed(self, message: TrendingPageChanged):
        self.current_trending_page += message.delta
        if self.current_trending_page < 1:
            self.current_trending_page = 1
        await self.refresh_dashboard()

    @on(DashboardItemClicked)
    async def handle_dashboard_item_clicked(self, message: DashboardItemClicked):
        if message.media_type == "riven":
            # Jump to library detail
            self.navigation_source = "dashboard"
            item_data = message.item_data
            tmdb_id = item_data.get("tmdb_id")
            if not tmdb_id and "parent_ids" in item_data:
                tmdb_id = item_data["parent_ids"].get("tmdb_id")
            
            if tmdb_id:
                self.app_state = "library"
                main_content = self.query_one(MainContent)
                main_content.item_data = {
                    "id": tmdb_id,
                    "media_type": "tv" if item_data.get("type") == "show" else item_data.get("type")
                }
                await self._refresh_current_item_data_and_ui(delay=0)
        else:
            # Jump to search detail
            self.app_state = "search"
            main_content = self.query_one(MainContent)
            main_content.item_data = message.item_data
            await self._refresh_current_item_data_and_ui(delay=0)

    def watch_app_state(self, new_state: Literal["welcome", "dashboard", "search", "library", "calendar", "settings"]) -> None:
        welcome_message = self.query_one("#welcome-message")
        search_subheader = self.query_one("#search-subheader")
        main_area = self.query_one("#main-area")
        sidebar = self.query_one(Sidebar)
        main_content = self.query_one(MainContent)
        search_input = self.query_one("#search-input")
        pagination_slot = self.query_one("#pagination-slot")
        settings_view = self.query_one(SettingsView)
        dashboard_view = self.query_one(DashboardView)
        dashboard_wrapper = self.query_one("#dashboard-wrapper")
        advanced_view = self.query_one(AdvancedView)

        welcome_message.display = False
        search_subheader.display = False
        main_area.display = False
        sidebar.display = False
        main_content.display = False
        pagination_slot.display = False
        settings_view.display = False
        dashboard_view.display = False
        dashboard_wrapper.display = False
        advanced_view.display = False
        
        sidebar.query_one("#sidebar-list-container").display = False
        sidebar.query_one("#sidebar-filters-container").display = False
        sidebar.query_one("#sidebar-calendar-container").display = False

        if new_state == "welcome":
            welcome_message.display = True
        elif new_state == "dashboard":
            dashboard_view.display = True
            dashboard_wrapper.display = True
            self.run_worker(self.refresh_dashboard())
        elif new_state == "advanced":
            advanced_view.display = True
        elif new_state == "search":
            search_subheader.display = True
            main_area.display = True
            sidebar.display = True 
            main_content.display = True 
            search_input.focus()
            main_content.query_one("#main-content-container").remove_children()
            main_content.query_one("#main-content-title").display = False
        elif new_state == "library":
            search_subheader.display = False 
            main_area.display = True
            sidebar.display = True 
            main_content.display = True 
            pagination_slot.display = True
        elif new_state == "calendar":
            search_subheader.display = False
            main_area.display = True
            sidebar.display = True 
            sidebar.show_calendar_summary()
            main_content.display = True
        elif new_state == "settings":
            settings_view.display = True
            if not settings_view.settings_data:
                settings_view.post_message(Button.Pressed(settings_view.query_one("#btn-refresh-settings")))

    @on(Button.Pressed, "#btn-header-dashboard")
    def on_dashboard_button_pressed(self) -> None: 
        self.app_state = "dashboard"

    @on(Button.Pressed, "#btn-header-search")
    def on_search_button_pressed(self) -> None: 
        self.app_state = "search"

    @on(Button.Pressed, "#btn-header-library")
    async def on_library_button_pressed(self) -> None: 
        self.log_message("Library button pressed.")
        self.app_state = "library" 
        
        sidebar = self.query_one(Sidebar)
        sidebar.show_library_filters()
        
        await self.show_library_items(refresh_cache=True)

    @on(Button.Pressed, "#btn-header-advanced")
    def on_advanced_button_pressed(self) -> None:
        self.app_state = "advanced"

    @on(Button.Pressed, "#btn-header-calendar")
    async def on_calendar_button_pressed(self) -> None:
        self.log_message("Calendar button pressed.")
        self.app_state = "calendar"
        await self.show_calendar(refresh_cache=True)

    @on(Button.Pressed, "#btn-header-settings")
    def on_settings_button_pressed(self) -> None:
        self.log_message("Settings button pressed.")
        self.app_state = "settings"

    def watch_base_title(self, new_title: str) -> None: 
        if self.spinner is not None:
            self.spinner.base_title = new_title
            if not self.spinner._spinner_task:
                self.spinner.title_widget.update(new_title)
        else:
            try:
                self.query_one("#header-title", Static).update(new_title)
            except NoMatches:
                pass

    def _reset_base_title(self) -> None:
        self.base_title = "Riven TUI"
        self._clear_notification_timer = None

    async def start_spinner(self, message: str = "Loading...", interval: float = TitleSpinner.DEFAULT_INTERVAL):
        if self._clear_notification_timer:
            self._clear_notification_timer.stop()
            self._clear_notification_timer = None
        if self.spinner is not None:
            await self.spinner.start(message, interval)

    def stop_spinner(self):
        if self.spinner is not None:
            self.spinner.stop()

    async def on_resize(self, event) -> None: 
        main_content = self.query_one(MainContent)
        try:
            _ = main_content.query_one("#poster-display", Static)
            self.log_message("Resize detected while poster visible. Debouncing poster refresh.")
            if self.post_message_debounce_timer:
                self.post_message_debounce_timer.stop()
            self.post_message_debounce_timer = self.set_timer(0.2, lambda: self.post_message(RefreshPoster()))
        except NoMatches:
            pass

    async def on_refresh_poster(self, message: RefreshPoster) -> None: 
        main_content = self.query_one(MainContent)
        try:
            _ = main_content.query_one("#poster-display", Static)
        except NoMatches:
            return 

        current_main_content_width = main_content.size.width
        if (
            main_content.last_chafa_width is None
            or abs(current_main_content_width - main_content.last_chafa_width) > 2
        ):
            self.log_message(f"Refreshing poster due to size change. Current width: {current_main_content_width}, Last Chafa width: {main_content.last_chafa_width}")
            await self.show_item_actions()
        else:
            self.log_message(f"Poster refresh skipped, width change not significant. Current width: {current_main_content_width}, Last Chafa width: {main_content.last_chafa_width}")

    @on(SearchSubmitted)
    async def handle_search(self, message: SearchSubmitted):
        self.log_message(f"Handling TMDB search for: '{message.query}'")
        
        self.app_state = "search" 
        sidebar = self.query_one(Sidebar)
        sidebar.query_one(ListView).clear() 

        main_content = self.query_one(MainContent)
        container = main_content.query_one("#main-content-container")
        await container.query("*").remove() 
        main_content.query_one("#main-content-title").display = False

        await self.start_spinner(f"Searching for '{message.query}'")
        
        results, error = await self.api.search_tmdb(message.query, self.settings.get("tmdb_bearer_token"))
        
        self.stop_spinner()
        if error:
            self.log_message(f"TMDB Search Error: {error}")
            self.notify(f"TMDB Error: {error}", severity="error")
            return

        self.log_message(f"TMDB search returned {len(results)} results.")
        
        results.sort(key=lambda x: x.get('popularity', 0) or 0, reverse=True)
        
        sidebar.update_results(message.query, results)
        self.log_message("Sidebar results updated.")

    async def _render_poster(self, container: Container, tmdb_data: dict):
        if self.chafa_available and tmdb_data.get("poster_path"):
            main_content = self.query_one(MainContent)
            poster_url = f"https://image.tmdb.org/t/p/w1280{tmdb_data['poster_path']}"
            
            main_content_width = main_content.size.width
            chafa_target_width = max(10, main_content_width - 6)

            chafa_max_width = self.settings.get("chafa_max_width", 0)
            if chafa_max_width > 0:
                chafa_target_width = min(chafa_target_width, chafa_max_width)
            
            poster_art, error = await self.api.get_poster_chafa(poster_url, width=chafa_target_width)
            if error:
                self.log_message(f"Error getting poster: {error}")
            else:
                await container.mount(Static(Text.from_ansi(poster_art), id="poster-display"))
                main_content.last_chafa_width = chafa_target_width

    async def show_item_actions(self):
        main_content = self.query_one(MainContent)
        title_widget = main_content.query_one("#main-content-title")
        container = main_content.query_one("#main-content-container")
        
        await container.query("*").remove()
        main_content.last_chafa_width = None 
        
        tmdb_data = main_content.tmdb_details
        riven_data = main_content.item_details
        search_item_data = main_content.item_data 

        if not tmdb_data:
            self.notify("Missing TMDB details.", severity="error")
            return

        title = tmdb_data.get('title') or tmdb_data.get('name', 'N/A')
        year = (tmdb_data.get('release_date') or tmdb_data.get('first_air_date', 'N/A'))[:4]
        runtime_movie = tmdb_data.get('runtime', 0) 
        
        episode_run_time = None
        if search_item_data and search_item_data.get("media_type") == "tv":
            episode_run_time_list = tmdb_data.get('episode_run_time', [])
            if episode_run_time_list:
                episode_run_time = f"{episode_run_time_list[0]} mins" 

        languages_spoken_list = [lang.get('iso_639_1').upper() for lang in tmdb_data.get('spoken_languages', []) if lang.get('iso_639_1')]
        if not languages_spoken_list and tmdb_data.get('original_language'):
            languages_spoken_list.append(tmdb_data.get('original_language').upper())
        languages_spoken = " - ".join(languages_spoken_list)

        status = tmdb_data.get('status')
        genres = " - ".join([genre.get('name') for genre in tmdb_data.get('genres', []) if genre.get('name')])

        description = tmdb_data.get('overview')
        tagline = tmdb_data.get('tagline')

        if riven_data:
            title_widget.display = True
            title_widget.update(f"In Library (Riven ID: {riven_data.get('id')})")
        else:
            title_widget.display = True
            title_widget.update("Not in Library")


        await container.mount(Static(f"[bold]{title}[/bold]", classes="media-title"))
        
        if tagline:
            await container.mount(Static(f"[italic]{tagline}[/italic]", classes="media-tagline")),

        action_buttons = []
        if riven_data:
            action_buttons.extend([
                Button("Delete", id="btn-delete", variant="error"),
                Button("Reset", id="btn-reset", variant="warning"),
                Button("Retry", id="btn-retry", variant="primary"),
            ])
        
        action_buttons.append(Button("Manual Scrape", id="btn-manual-scrape", variant="success"))
        if not riven_data:
            action_buttons.append(Button("Add to Library", id="btn-add", variant="success"))

        if self.app_state == "library" or self.navigation_source == "dashboard":
            action_buttons.append(Button("Back", id="btn-back-to-library", variant="primary"))

        action_buttons.append(Button("Print TMDB JSON", id="btn-print-json"))
        
        if action_buttons:
            await container.mount(Horizontal(*action_buttons, classes="media-button-bar"))

        metadata_items = [year]
        if search_item_data and search_item_data.get("media_type") == "movie" and runtime_movie:
            metadata_items.append(f"{runtime_movie} mins")
        elif search_item_data and search_item_data.get("media_type") == "tv" and episode_run_time:
            metadata_items.append(episode_run_time)
        if languages_spoken:
            metadata_items.append(languages_spoken)
        if status:
            metadata_items.append(status)
        
        if metadata_items:
            await container.mount(Static(" * ".join(filter(None, metadata_items)), classes="media-metadata")),

        if genres:
            await container.mount(Static(f"Genres: {genres}", classes="media-genres")),

        if description:
            await container.mount(Static(description, classes="media-overview")),

        await self._render_poster(container, tmdb_data)

    @on(ListView.Selected, "#sidebar-list")
    async def on_list_view_selected(self, event: ListView.Selected) -> None: 

        main_content = self.query_one(MainContent)
        
        selected_item_label = event.item.name

        if selected_item_label == "Logs":
            self.log_message("Logs selected.")
            await self.show_initial_logs()
            return

        if selected_item_label == "Settings":
            self.log_message("Settings selected.")
            self.app_state = "settings"
            return
            
        if not (hasattr(event.item, "item_data") and event.item.item_data):
            return
        
        tmdb_search_result = event.item.item_data
        main_content.item_data = tmdb_search_result
        
        await self._refresh_current_item_data_and_ui(delay=0)

    async def _refresh_current_item_data_and_ui(self, delay: float | None = None) -> None:
        effective_delay = delay if delay is not None else self.refresh_delay_seconds

        main_content = self.query_one(MainContent)
        tmdb_search_result = main_content.item_data

        if not tmdb_search_result:
            self.log_message("No item data available to refresh.")
            return

        tmdb_id = tmdb_search_result.get("id")
        media_type = tmdb_search_result.get("media_type")

        if not media_type or not tmdb_id:
            self.notify("Current item is missing ID or media type for refresh.", severity="error")
            return

        await self.start_spinner("Repulling item data...")
        await asyncio.sleep(effective_delay) 

        tmdb_details, error = await self.api.get_tmdb_details(media_type, tmdb_id, self.settings.get("tmdb_bearer_token"))

        if error:
            self.log_message(f"TMDB Details Error during repull: {error}")
            self.notify(f"TMDB Error during repull: {error}", severity="error")
            main_content.tmdb_details = None 
            main_content.item_details = None 
            self.stop_spinner()
            await self.show_item_actions()
            return

        main_content.tmdb_details = tmdb_details
        self.log_message("Successfully re-pulled TMDB details.")

        riven_media_type = "tv" if media_type == "tv" else "movie"
        riven_id_to_check = tmdb_details.get("external_ids", {}).get("tvdb_id") if media_type == "tv" else tmdb_id
        
        if not riven_id_to_check:
            self.log_message(f"Could not find a suitable ID to check against Riven library during repull (media_type: {media_type}).")
            main_content.item_details = None
        else:
            self.log_message(f"Checking Riven library for {riven_media_type} with id {riven_id_to_check}")
            main_content.item_details = await self.api.get_item_by_id(riven_media_type, str(riven_id_to_check), self.settings.get("api_key"))

        self.log_message(f"Riven library repull complete. Found: {'Yes' if main_content.item_details else 'No'}")
        
        self.stop_spinner() 
        await self.show_item_actions() 

    @on(Button.Pressed, "#btn-apply-filters")
    async def on_apply_filters(self):
        sidebar = self.query_one(Sidebar)
        filters = sidebar.get_filter_values()
        
        try:
            limit = int(filters["limit"]) if filters["limit"] else 20
            page = int(filters["page"]) if filters["page"] else 1
        except ValueError:
            self.notify("Page must be a number", severity="error")
            return

        await self.show_library_items(
            limit=limit,
            page=page,
            sort=filters["sort"],
            item_type=filters["type"],
            search=filters["search"],
            states=[filters["states"]] if filters["states"] else None,
            count_only=filters["count_only"]
        )

    async def show_library_items(self, limit: int = 20, page: int = 1, sort: str = "date_desc", item_type: str | None = None, search: str | None = None, states: List[str] | None = None, count_only: bool = False, refresh_cache: bool = False) -> None:
        self.last_library_filters = {
            "limit": limit,
            "page": page,
            "sort": sort,
            "item_type": item_type,
            "search": search,
            "states": states,
            "count_only": count_only
        }

        main_content = self.query_one(MainContent)
        container = main_content.query_one("#main-content-container")
        
        if not self.library_cache or refresh_cache:
            await container.query("*").remove() 
            await self.start_spinner("Fetching full library...")
            
            api_key = self.settings.get("api_key")
            self.library_cache = []
            
            async def fetch_full(t):
                resp, err = await self.api.get_items(
                    api_key, limit=999999, page=1, sort="date_desc", 
                    item_type=t, extended=False
                )
                return resp.get("items", []) if resp else []

            results = await asyncio.gather(fetch_full("movie"), fetch_full("show"))
            self.library_cache = results[0] + results[1]
            
            self.stop_spinner()
            self.log_message(f"Library cache refreshed: {len(self.library_cache)} items total.")

        filtered_items = self.library_cache
        
        if item_type:
            filtered_items = [i for i in filtered_items if i.get("type") == item_type]
        
        if search:
            search_query = search.lower()
            filtered_items = [i for i in filtered_items if search_query in (i.get("title") or "").lower()]
            
        if states and states[0]:
            filtered_items = [i for i in filtered_items if i.get("state") in states]

        is_reverse = "desc" in sort
        
        if "title" in sort:
            filtered_items.sort(
                key=lambda x: ((x.get('title') or '').lower(), x.get('requested_at') or '0000-00-00 00:00:00'), 
                reverse=is_reverse
            )
        else:
            filtered_items.sort(
                key=lambda x: (x.get('requested_at') or '0000-00-00 00:00:00', (x.get('title') or '').lower()), 
                reverse=is_reverse
            )

        total_count = len(filtered_items)
        total_pages = math.ceil(total_count / limit) if limit > 0 else 1
        
        if page > total_pages: page = total_pages
        if page < 1: page = 1
        
        self.last_library_filters["page"] = page

        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        paged_items = filtered_items[start_idx:end_idx]

        await container.query("*").remove()

        if count_only:
            await container.mount(Static(f"Total count: {total_count}"))
            self.notify(f"Count: {total_count}", severity="information")
            return

        if not paged_items:
            await container.mount(Static("No items found matching current filters."))
            self.notify("No matches found.", severity="information")
        else:
            for item in paged_items:
                title = item.get("title", "N/A")
                media_type = item.get("type", "N/A")
                state = item.get("state", "N/A")
                content_rating = item.get("content_rating", "N/A")

                aired_at_year = "N/A"
                if item.get("aired_at"):
                    try:
                        aired_at_year = item["aired_at"].split('-')[0]
                    except IndexError:
                        pass 

                item_display_widget = LibraryItemCard(
                    item_data=item,
                    renderable=f"[bold]{title}[/bold] ({aired_at_year})\n"
                               f"State: {state} | Content Rating: {content_rating}",
                    classes="library-item-card"
                )
                item_display_widget.add_class(f"library-item-{media_type}")
                await container.mount(item_display_widget)
        
        pagination_slot = self.query_one("#pagination-slot")
        await pagination_slot.query("*").remove()
        await pagination_slot.mount(PaginationControl(page, total_pages))
        
        self.log_message(f"Displaying library: {len(paged_items)}/{total_count} items (Page {page}/{total_pages})")

    @on(LibraryItemCard.Clicked)
    async def on_library_item_clicked(self, event: LibraryItemCard.Clicked) -> None:
        self.navigation_source = "library"
        item_data = event.item_data
        
        tmdb_id = item_data.get("tmdb_id")
        if not tmdb_id and "parent_ids" in item_data:
            tmdb_id = item_data["parent_ids"].get("tmdb_id")
            
        media_type = item_data.get("type")

        if not tmdb_id:
            external_id = item_data.get("tvdb_id") or (item_data.get("parent_ids") or {}).get("tvdb_id")
            source = "tvdb_id"
            
            if not external_id:
                external_id = item_data.get("imdb_id") or (item_data.get("parent_ids") or {}).get("imdb_id")
                source = "imdb_id"
            
            if external_id:
                self.log_message(f"Attempting to resolve TMDB ID via {source}: {external_id}")
                self.notify(f"Resolving TMDB ID for '{item_data.get('title')}'...", severity="information")
                resolved_id, err = await self.api.find_tmdb_id(str(external_id), source, self.settings.get("tmdb_bearer_token"))
                if resolved_id:
                    tmdb_id = resolved_id
                    self.log_message(f"Resolved TMDB ID: {tmdb_id}")
                else:
                    self.log_message(f"TMDB Resolution Error: {err}")

        self.log_message(f"Library Item Clicked: {item_data.get('title')} (Riven ID: {item_data.get('id')}, TMDB ID: {tmdb_id})")
        
        if not tmdb_id:
            self.notify(f"No TMDB ID found for '{item_data.get('title')}'. Cannot fetch details.", severity="warning")
            return
            
        main_content = self.query_one(MainContent)
        main_content.item_data = {
            "id": tmdb_id,
            "media_type": "tv" if media_type == "show" else media_type
        }
        
        await self._refresh_current_item_data_and_ui(delay=0)

    @on(Button.Pressed, "#btn-back-to-library")
    async def handle_back_to_library(self):
        if self.navigation_source == "dashboard":
            self.app_state = "dashboard"
        elif self.navigation_source == "library":
            if self.last_library_filters:
                await self.show_library_items(**self.last_library_filters)
            else:
                await self.show_library_items()
        else:
            self.app_state = "library"

    async def show_initial_logs(self):
        self.log_message("Fetching initial logs...")
        url, error = await self.api.upload_logs(self.settings.get("api_key"))
        if error:
            if "[Errno -3]" in error:
                self.notify("Error: DNS lookup failed. Check your internet connection.", severity="error")
            else:
                self.notify(f"Error uploading logs: {error}", severity="error")
            self.log_message(f"Error uploading logs: {error}")
            return

        logs, error = await self.api.get_logs_from_url(url)
        if error:
            self.log_message(f"Error fetching logs from URL: {error}")
            self.notify(f"Error fetching logs from URL: {error}", severity="error")
            return
        
        self.previous_logs = logs
        limit = self.settings.get("log_display_limit", 20)
        log_lines = logs.splitlines()
        display_logs = "\n".join(log_lines[-limit:])
        
        main_content = self.query_one(MainContent)
        await main_content.display_logs(display_logs)
        self.log_message("Initial logs displayed.")

    @on(Button.Pressed, "#btn-prev-page")
    async def on_prev_page_click(self, event: Button.Pressed):
        self.log_message("App: Prev button pressed handler triggered.")
        event.stop()
        if self.last_library_filters:
            current_page = self.last_library_filters.get("page", 1)
            if current_page > 1:
                new_page = current_page - 1
                try:
                    self.query_one("#lib-filter-page", Input).value = str(new_page)
                except: pass
                self.post_message(PageChanged(new_page))
            else:
                self.log_message("App: Already on first page.")

    @on(Button.Pressed, "#btn-next-page")
    async def on_next_page_click(self, event: Button.Pressed):
        self.log_message("App: Next button pressed handler triggered.")
        event.stop()
        if self.last_library_filters:
            current_page = self.last_library_filters.get("page", 1)
            new_page = current_page + 1
            try:
                self.query_one("#lib-filter-page", Input).value = str(new_page)
            except: pass
            self.post_message(PageChanged(new_page))

    @on(MonthChanged)
    async def on_month_changed(self, event: MonthChanged):
        self.log_message(f"Month changed to {event.month}/{event.year}")
        self.current_calendar_date = datetime(event.year, event.month, 1)
        await self.show_calendar()

    @on(FilterPill.Changed)
    async def on_calendar_filter_changed(self, event: FilterPill.Changed):
        self.calendar_filters[event.filter_type] = event.value
        await self.show_calendar()

    async def show_calendar(self, refresh_cache: bool = False) -> None:
        main_content = self.query_one(MainContent)
        container = main_content.query_one("#main-content-container")
        
        if not self.calendar_cache or refresh_cache:
            await container.query("*").remove()
            await self.start_spinner("Fetching calendar...")
            
            api_key = self.settings.get("api_key")
            resp, err = await self.api.get_calendar(api_key)
            
            if err:
                self.log_message(f"Calendar Fetch Error: {err}")
                self.notify(f"Error fetching calendar: {err}", severity="error")
                self.stop_spinner()
                return
            
            if isinstance(resp, dict) and "data" in resp:
                self.calendar_cache = list(resp["data"].values())
            else:
                self.calendar_cache = []
                
            self.stop_spinner()
            self.log_message(f"Calendar cache refreshed: {len(self.calendar_cache)} items.")

        year = self.current_calendar_date.year
        month = self.current_calendar_date.month
        
        monthly_items = []
        for item in self.calendar_cache:
            i_type = item.get("item_type")
            if i_type and not self.calendar_filters.get(i_type, True):
                continue

            aired_at_str = item.get("aired_at")
            if aired_at_str:
                try:
                    if "T" in aired_at_str:
                        dt = datetime.fromisoformat(aired_at_str)
                    else:
                        dt = datetime.strptime(aired_at_str, "%Y-%m-%d %H:%M:%S")
                    
                    if dt.year == year and dt.month == month:
                        item["_dt"] = dt
                        monthly_items.append(item)
                except ValueError:
                    continue

        monthly_items.sort(key=lambda x: x["_dt"])

        grouped_items: Dict[str, List[dict]] = {}
        for item in monthly_items:
            date_key = item["_dt"].strftime("%a, %B %d")
            if date_key not in grouped_items:
                grouped_items[date_key] = []
            grouped_items[date_key].append(item)

        await container.query("*").remove()
        
        await container.mount(CalendarHeader(year, month))
        
        legend_row = Horizontal(id="calendar-legend-row")
        await container.mount(legend_row)
        
        filters = [
            ("movie", "Movies"),
            ("episode", "Episodes"),
            ("show", "Shows"),
            ("season", "Seasons"),
        ]
        
        for f_type, label in filters:
            pill = FilterPill(label, value=self.calendar_filters[f_type], filter_type=f_type)
            await legend_row.mount(pill)

        sidebar = self.query_one(Sidebar)
        await sidebar.update_calendar_sidebar(year, month, monthly_items, self.calendar_filters)

        if not monthly_items:
            await container.mount(Static(f"No items found for {calendar.month_name[month]} {year}.", id="calendar-no-items"))
        else:
            for date_str, items in grouped_items.items():
                day_num = items[0]["_dt"].day
                day_group = Vertical(classes="calendar-day-group", id=f"day-group-{day_num}")
                await container.mount(day_group)
                
                header_row = Horizontal(classes="calendar-day-header")
                await day_group.mount(header_row)
                await header_row.mount(Label(date_str, classes="calendar-date-label"))
                await header_row.mount(Label(f"{len(items)} item{'s' if len(items) > 1 else ''}", classes="calendar-count-label"))
                
                for item in items:
                    await day_group.mount(CalendarItemCard(item))

    @on(Button.Pressed, "#btn-prev-year-sidebar")
    async def on_prev_year_sidebar(self):
        self.current_calendar_date = self.current_calendar_date.replace(year=self.current_calendar_date.year - 1)
        await self.show_calendar()

    @on(Button.Pressed, "#btn-next-year-sidebar")
    async def on_next_year_sidebar(self):
        self.current_calendar_date = self.current_calendar_date.replace(year=self.current_calendar_date.year + 1)
        await self.show_calendar()

    @on(Button.Pressed, "#btn-prev-month-sidebar")
    async def on_prev_month_sidebar(self):
        new_month = self.current_calendar_date.month - 1
        new_year = self.current_calendar_date.year
        if new_month < 1:
            new_month = 12
            new_year -= 1
        self.current_calendar_date = self.current_calendar_date.replace(year=new_year, month=new_month)
        await self.show_calendar()

    @on(Button.Pressed, "#btn-next-month-sidebar")
    async def on_next_month_sidebar(self):
        new_month = self.current_calendar_date.month + 1
        new_year = self.current_calendar_date.year
        if new_month > 12:
            new_month = 1
            new_year += 1
        self.current_calendar_date = self.current_calendar_date.replace(year=new_year, month=new_month)
        await self.show_calendar()

    @on(DayClicked)
    def on_day_grid_click(self, event: DayClicked):
        day_num = event.day
        try:
            target_id = f"#day-group-{day_num}"
            main_content = self.query_one(MainContent)
            container = main_content.query_one("#main-content-container")
            day_widget = container.query_one(target_id)
            main_content.scroll_to_widget(day_widget)
            self.notify(f"Jumping to {calendar.month_name[self.current_calendar_date.month]} {day_num}", severity="information")
        except NoMatches:
            self.notify(f"No content on day {day_num}", severity="warning")

    @on(PageChanged)
    async def on_page_changed(self, event: PageChanged):
        self.log_message(f"Page changed message received: {event.page}")
        self.notify(f"Navigating to page {event.page}...", severity="information")
        if not self.last_library_filters:
            self.log_message("last_library_filters is empty in on_page_changed. Initializing with defaults.")
            self.last_library_filters = {"page": 1, "limit": 20}
        
        self.last_library_filters["page"] = event.page
        
        try:
            page_input = self.query_one("#lib-filter-page", Input)
            page_input.value = str(event.page)
        except Exception as e:
            self.log_message(f"Error updating filter input: {e}")
            
        await self.show_library_items(**self.last_library_filters)

    @on(Button.Pressed, "#btn-refresh-logs")
    async def refresh_logs(self):
        self.log_message("Refreshing logs...")
        url, error = await self.api.upload_logs(self.settings.get("api_key"))
        if error:
            if "[Errno -3]" in error:
                self.notify("Error: DNS lookup failed. Check your internet connection.", severity="error")
            else:
                self.notify(f"Error uploading logs: {error}", severity="error")
            self.log_message(f"Error uploading logs: {error}")
            return

        logs, error = await self.api.get_logs_from_url(url)
        if error:
            self.log_message(f"Error fetching logs from URL: {error}")
            self.notify(f"Error fetching logs from URL: {error}", severity="error")
            return
        
        if logs != self.previous_logs:
            previous_lines = self.previous_logs.splitlines()
            new_lines = logs.splitlines()
            
            diff = new_lines[len(previous_lines):]
            
            if diff:
                log_content = self.query_one("#log-content", Static)
                current_content = log_content.render()
                new_content = str(current_content) + "\n" + "\n".join(diff)
                log_content.update(new_content)

            self.previous_logs = logs
            self.log_message("Logs refreshed with new content.")
        else:
            self.log_message("No new logs.")
            self.notify("No new logs.")

    @on(Button.Pressed, "#btn-print-json")
    async def handle_print_json(self):
        main_content = self.query_one(MainContent)
        if main_content.tmdb_details:
            self.log_message("Displaying full TMDB JSON for item.")
            await main_content.display_json(main_content.tmdb_details)

    @on(Button.Pressed, "#btn-back-to-actions")
    async def handle_back_to_actions(self):
        self.log_message("Returning to item actions view.")
        await self.show_item_actions()

    @on(Button.Pressed, "#btn-main-back")
    async def handle_main_back(self):
        main_content = self.query_one(MainContent)
        container = main_content.query_one("#main-content-container")
        await container.query("*").remove()
        main_content.query_one("#main-content-title").display = False

    @on(Button.Pressed, "#btn-delete")
    async def handle_delete(self):
        main_content = self.query_one(MainContent)
        item_id = main_content.item_details.get("id")
        if not item_id: return

        self.log_message(f"Deleting item {item_id}...")
        success, response = await self.api.delete_item(item_id, self.settings.get("api_key"))
        if success:
            self.log_message(f"Item {item_id} deleted. Response: {response}")
            self.notify(f"Item deleted.", severity="information")
            
            main_content.item_details = None 
            await self._refresh_current_item_data_and_ui(delay=self.refresh_delay_seconds) 
        else:
            self.log_message(f"Failed to delete item {item_id}. API Response: {response}")
            self.notify("Failed to delete item. Check debug log.", severity="error")

    @on(Button.Pressed, "#btn-reset")
    async def handle_reset(self):
        main_content = self.query_one(MainContent)
        item_id = main_content.item_details.get("id")
        if not item_id: return

        self.log_message(f"Resetting item {item_id}...")
        success, response = await self.api.reset_item(item_id, self.settings.get("api_key"))
        if success:
            self.log_message(f"Item {item_id} reset. Response: {response}")
            self.notify("Item reset successfully.", severity="information")
            
            await self._refresh_current_item_data_and_ui(delay=self.refresh_delay_seconds) 
        else:
            self.log_message(f"Failed to reset item {id}. API Response: {response}")
            self.notify("Failed to reset item. Check debug log.", severity="error")

    @on(Button.Pressed, "#btn-retry")
    async def handle_retry(self):
        main_content = self.query_one(MainContent)
        item_id = main_content.item_details.get("id")
        if not item_id: return

        self.log_message(f"Retrying item {item_id}...")
        success, response = await self.api.retry_item(item_id, self.settings.get("api_key"))
        if success:
            self.log_message(f"Item {item_id} retried. Response: {response}")
            self.notify("Item sent for retry.", severity="information")
            
            await self._refresh_current_item_data_and_ui(delay=self.refresh_delay_seconds) 
        else:
            self.log_message(f"Failed to retry item {item_id}. API Response: {response}")
            self.notify("Failed to retry item. Check debug log.", severity="error")

    @on(Button.Pressed, "#btn-manual-scrape")
    def handle_manual_scrape_button(self):
        self.log_message("Manual Scrape button pressed.")
        self.run_worker(self._run_manual_scrape)

    async def _run_manual_scrape(self):
        self.log_message("Worker: Starting manual scrape logic.")
        main_content = self.query_one(MainContent)
        if not main_content.tmdb_details:
            self.log_message("Error: No TMDB details found in MainContent.")
            self.notify("No TMDB details available for scraping.", severity="error")
            return

        tmdb_id = main_content.tmdb_details.get("id")
        riven_item_id = main_content.item_details.get("id") if main_content.item_details else None
        media_type = main_content.item_data.get("media_type")

        if not media_type:
            self.log_message("Error: Media type not found in item_data.")
            self.notify("Media type not found.", severity="error")
            return
        
        self.log_message(f"Starting manual scrape for {media_type} TMDB ID: {tmdb_id} (Library ID: {riven_item_id})")

        tvdb_id_for_scrape = None
        if media_type == "tv" and not riven_item_id:
            tvdb_id_for_scrape = main_content.tmdb_details.get("external_ids", {}).get("tvdb_id")
            if not tvdb_id_for_scrape:
                self.log_message(f"Error: Missing TVDB ID for TV show {tmdb_id}")
                self.stop_spinner()
                self.notify(f"Could not find TVDB ID for {main_content.tmdb_details.get('name')} to scrape.", severity="error")
                self.base_title = "Riven TUI - Missing TVDB ID!"
                self._clear_notification_timer = self.set_timer(NOTIFICATION_CLEAR_DELAY, self._reset_base_title)
                return

        await self.start_spinner("Discovering streams...")
        self.log_message("Pushing ScrapeLogScreen.")
        log_screen = ScrapeLogScreen()
        self.push_screen(log_screen)
        log_widget = log_screen.query_one(Log)

        all_streams = {}
        self.log_message("Starting stream discovery loop.")
        try:
            async for line in self.api.scrape_stream(media_type, tmdb_id, self.settings.get("api_key"), riven_item_id, tvdb_id=tvdb_id_for_scrape):
                if line.startswith("data:"):
                    data_content = line[len("data:"):].strip()
                    if data_content == "[DONE]":
                        self.log_message("Discovery loop: [DONE] received.")
                        log_widget.write_line("Stream discovery complete.")
                        break
                    
                    try:
                        message_data = json.loads(data_content)
                        if 'message' in message_data:
                            log_widget.write_line(f"-> {message_data['message']}")
                        if 'streams' in message_data and message_data['streams']:
                            all_streams.update(message_data['streams'])
                            self.log_message(f"Discovery loop: Found {len(message_data['streams'])} streams.")
                    except json.JSONDecodeError:
                        continue

                elif line.startswith("error:"):
                    self.log_message(f"Discovery loop error: {line}")
                    log_widget.write_line(f"ERROR: {line}")

        except Exception as e:
            self.log_message(f"Unexpected error in discovery loop: {e}")
            log_widget.write_line(f"Unexpected error: {e}")
        
        self.log_message(f"Discovery complete. Total streams found: {len(all_streams)}")
        self.app.pop_screen() 

        streams = list(all_streams.values())
        if not streams:
            self.notify("No streams found.", severity="warning")
            return

        session_data = None
        while True:
            selection_screen = StreamSelectionScreen(streams)
            magnet_link = await self.app.push_screen_wait(selection_screen)

            if not magnet_link:
                self.notify("Manual scrape cancelled.", severity="info")
                self.base_title = "Riven TUI - Manual Scrape Cancelled" 
                self._clear_notification_timer = self.set_timer(NOTIFICATION_CLEAR_DELAY, self._reset_base_title)
                return

            self.notify("Starting scrape session...")
            await self.start_spinner("Starting scrape session...")
            current_session_data, error = await self.api.start_scrape_session(media_type, magnet_link, tmdb_id, self.settings.get("api_key"), riven_item_id, tvdb_id=tvdb_id_for_scrape)
            self.stop_spinner()

            if error and "Torrent is not cached" in error:
                self.notify("Torrent not cached. Please select another.", severity="warning")
                self.base_title = "Riven TUI - Scrape Session Failed (Torrent Not Cached)"
                self._clear_notification_timer = self.set_timer(NOTIFICATION_CLEAR_DELAY, self._reset_base_title)
                continue 
            elif error or not isinstance(current_session_data, dict):
                self.notify(f"Error starting session: {error or 'Invalid response'}", severity="error")
                self.base_title = "Riven TUI - Scrape Session Error!"
                self._clear_notification_timer = self.set_timer(NOTIFICATION_CLEAR_DELAY, self._reset_base_title)
                return
            else:
                self.base_title = "Riven TUI - Scrape Session Started!"
                self._clear_notification_timer = self.set_timer(NOTIFICATION_CLEAR_DELAY, self._reset_base_title)

            session_data = current_session_data
            break

        session_id = session_data.get("session_id")
        containers_files = session_data.get("containers", {}).get("files", [])
        
        if not session_id or not containers_files:
            self.notify("No cached files found in session.", severity="error")
            self.base_title = "Riven TUI - No Cached Files for Scrape!"
            self._clear_notification_timer = self.set_timer(NOTIFICATION_CLEAR_DELAY, self._reset_base_title)
            return

        if media_type == "movie":
            video_file = max(containers_files, key=lambda f: f.get('filesize', 0))
            file_id_str = str(video_file.get("file_id"))

            self.log_message(f"Selected cached file: {video_file.get('filename')}")
            
            await self.api.parse_torrent_titles([video_file.get('filename')], self.settings.get("api_key"))

            payload_for_select = {
                file_id_str: {
                    "file_id": video_file.get("file_id"),
                    "filename": video_file.get("filename"),
                    "filesize": video_file.get("filesize"),
                    "download_url": video_file.get("download_url")
                }
            }

            success, response = await self.api.select_scrape_file(session_id, payload_for_select, self.settings.get("api_key") )
            if success:
                await self.start_spinner("Updating scrape attributes...")
                update_payload = payload_for_select[file_id_str]
                await self.api.update_scrape_attributes(session_id, update_payload, self.settings.get("api_key") )
                self.stop_spinner()
                self.base_title = "Riven TUI - Scrape Attributes Updated!"
                self._clear_notification_timer = self.set_timer(NOTIFICATION_CLEAR_DELAY, self._reset_base_title)
                
                await self.start_spinner("Completing scrape session...")
                final_success, final_response = await self.api.complete_scrape_session(session_id, self.settings.get("api_key") )
                self.stop_spinner()
                if final_success:
                    self.notify("Manual scrape initiated successfully!", severity="success")
                    self.base_title = "Riven TUI - Scrape Completed Successfully!"
                    self._clear_notification_timer = self.set_timer(NOTIFICATION_CLEAR_DELAY, self._reset_base_title)
                    
                    await self._refresh_current_item_data_and_ui(delay=self.refresh_delay_seconds) 
                else:
                    self.notify(f"Finalization Error: {final_response}", severity="error")
                    self.base_title = f"Riven TUI - Scrape Finalization Error: {final_response}!"
                    self._clear_notification_timer = self.set_timer(NOTIFICATION_CLEAR_DELAY, self._reset_base_title)
            else:
                self.notify(f"Error selecting file: {response}", severity="error")
                self.base_title = "Riven TUI - Error Selecting File for Scrape!"
                self._clear_notification_timer = self.set_timer(NOTIFICATION_CLEAR_DELAY, self._reset_base_title)
        
        elif media_type == "tv":
            filenames = [f.get("filename") for f in containers_files if f.get("filename")]
            response, error = await self.api.parse_torrent_titles(filenames, self.settings.get("api_key"))
            
            if error:
                self.notify(f"Error parsing titles: {error}", severity="error")
                self.base_title = "Riven TUI - Error Parsing Torrent Titles!"
                self._clear_notification_timer = self.set_timer(NOTIFICATION_CLEAR_DELAY, self._reset_base_title)
                return
            parsed_files = response.get("data", [])

            title = main_content.tmdb_details.get('name', 'N/A')
            mapping_screen = FileMappingScreen(containers_files, parsed_files, title, session_id)
            file_mapping = await self.app.push_screen_wait(mapping_screen)

            if not file_mapping:
                self.notify("File mapping cancelled.", severity="info")
                self.base_title = "Riven TUI - File Mapping Cancelled!"
                self._clear_notification_timer = self.set_timer(NOTIFICATION_CLEAR_DELAY, self._reset_base_title)
                return
            
            payload_for_select = {}
            for season in file_mapping:
                for episode in file_mapping[season]:
                    file_data = file_mapping[season][episode]
                    file_id_str = str(file_data.get("file_id"))
                    payload_for_select[file_id_str] = file_data

            success, response = await self.api.select_scrape_file(session_id, payload_for_select, self.settings.get("api_key") )
            if success:
                await self.start_spinner("Updating scrape attributes...")
                await self.api.update_scrape_attributes(session_id, file_mapping, self.settings.get("api_key") )
                self.stop_spinner()
                self.base_title = "Riven TUI - Scrape Attributes Updated!"
                self._clear_notification_timer = self.set_timer(NOTIFICATION_CLEAR_DELAY, self._reset_base_title)
                
                await self.start_spinner("Completing scrape session...")
                final_success, final_response = await self.api.complete_scrape_session(session_id, self.settings.get("api_key") )
                self.stop_spinner()
                if final_success:
                    self.notify("Manual scrape for TV show initiated successfully!", severity="success")
                    self.base_title = "Riven TUI - Scrape Completed Successfully!"
                    self._clear_notification_timer = self.set_timer(NOTIFICATION_CLEAR_DELAY, self._reset_base_title)

                    await self._refresh_current_item_data_and_ui(delay=self.refresh_delay_seconds) 
                else:
                    self.notify(f"Finalization Error: {final_response}", severity="error")
                    self.base_title = f"Riven TUI - Scrape Finalization Error: {final_response}!"
                    self._clear_notification_timer = self.set_timer(NOTIFICATION_CLEAR_DELAY, self._reset_base_title)
            else:
                self.notify(f"Error selecting files: {response}", severity="error")
                self.base_title = "Riven TUI - Error Selecting Files for Scrape!"
                self._clear_notification_timer = self.set_timer(NOTIFICATION_CLEAR_DELAY, self._reset_base_title)


    @on(Button.Pressed, "#btn-add")
    async def handle_add(self):
        main_content = self.query_one(MainContent)
        if not main_content.tmdb_details:
            self.notify("No TMDB details to add.", severity="error")
            return

        tmdb_details = main_content.tmdb_details
        media_type = main_content.item_data.get("media_type")
        
        add_media_type = "tv" if media_type == "tv" else "movie"
        id_to_add = tmdb_details.get("external_ids", {}).get("tvdb_id") if media_type == "tv" else tmdb_details.get("id")
        id_type = "tvdb_ids" if media_type == "tv" else "tmdb_ids"
        title = tmdb_details.get("name") or tmdb_details.get("title")

        if not id_to_add:
            self.notify(f"Could not find a TVDB ID for {title} to add it to Riven.", severity="error")
            return

        self.log_message(f"Adding item '{title}'. Type: {add_media_type}, ID Type: {id_type}, ID: {id_to_add}")
        self.notify(f"Adding '{title}' to library...")
        success, response = await self.api.add_item(add_media_type, id_type, str(id_to_add), self.settings.get("api_key") )

        if success:
            self.log_message("Item added successfully. Refreshing view.")
            self.notify("Item added successfully! Refreshing...", severity="information")
            
            await self._refresh_current_item_data_and_ui(delay=10) 
        else:
            self.log_message(f"Failed to add item. API response: {response}")
            self.notify("Failed to add item.", severity="error")


if __name__ == "__main__":
    RivenTUI().run()
