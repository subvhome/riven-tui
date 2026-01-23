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
from textual.widgets import Header, Footer, Static, Input, ListView, ListItem, Label, Button, Log, Markdown, Select, Checkbox, ProgressBar, RichLog
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.css.query import NoMatches
from textual.screen import ModalScreen
from textual.reactive import reactive
from textual.timer import Timer
from rich.text import Text
from rich.markup import escape

from api import RivenAPI
from settings_view import SettingsView
from dashboard_view import DashboardView
from advanced_view import AdvancedView
from search_grid import SearchGridTile, HOVER_DELAY
from version import VERSION
from messages import (
    RefreshPoster, LogMessage, CalendarItemSelected, 
    MonthChanged, ToggleLibrarySelection, PageChanged
)
from logs_view import LogsView
from calendar_view import CalendarItemCard, CalendarHeader
from sidebar import Sidebar, FilterPill
from search import SearchSubmitted
from search_results import LibraryItemCard
from modals import (
    UpdateScreen, MediaCardScreen, ScrapeLogScreen, 
    StreamSelectionScreen, FileMappingScreen, ChafaCheckScreen,
    ConfirmationScreen
)
import subprocess
import httpx

NOTIFICATION_CLEAR_DELAY = 10.0 # Seconds

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


class MainContent(Vertical):
    
    item_details: Optional[dict] = None 
    tmdb_details: Optional[dict] = None 
    item_data: Optional[dict] = None 
    last_chafa_width: Optional[int] = None 

    def compose(self) -> ComposeResult:
        
        # New Search Grid View Components
        with Vertical(id="centered-search-container", classes="hidden"):
            yield Input(placeholder="Search TMDB...", id="grid-search-input")
            yield Label(f"Hover over a tile for {HOVER_DELAY} seconds to preview poster", id="search-hover-hint")

        with VerticalScroll(id="search-grid-scroll", classes="hidden"):
            yield Container(id="search-grid-container")

        with Vertical(id="main-content-scroll-area"):
            yield Vertical(id="main-content-container")
            yield ListView(id="library-list", classes="hidden")
            yield Vertical(id="main-content-json-container", classes="hidden")
        yield Button("Back", id="btn-back-to-actions", variant="primary", classes="hidden")

    async def display_logs(self, logs: str):
        container = self.query_one("#main-content-container")
        await container.query("*").remove()
        await container.mount(Static(logs, id="log-content", expand=True))
        await container.mount(Button("Refresh", id="btn-refresh-logs", variant="primary"))

    async def display_json(self, data: dict):
        container = self.query_one("#main-content-container")
        lib_list = self.query_one("#library-list")
        json_container = self.query_one("#main-content-json-container")
        back_btn = self.query_one("#btn-back-to-actions")

        await json_container.query("*").remove()
        formatted_json = json.dumps(data, indent=4)
        await json_container.mount(Static(formatted_json))

        container.add_class("hidden")
        lib_list.add_class("hidden")
        json_container.remove_class("hidden")
        back_btn.remove_class("hidden")

    @on(Button.Pressed, "#btn-back-to-actions")
    async def handle_back_to_actions(self):
        self.reset_view()

    def reset_view(self):
        self.remove_class("media-details-active")
        self.query_one("#main-content-container").remove_class("hidden")
        self.query_one("#library-list").add_class("hidden")
        self.query_one("#main-content-json-container").add_class("hidden")
        self.query_one("#btn-back-to-actions").add_class("hidden")

from search_grid import SearchGridTile, HOVER_DELAY

class RedactingFormatter(logging.Formatter):
    def __init__(self, fmt=None, datefmt=None, style='%', patterns=None):
        super().__init__(fmt, datefmt, style)
        self.patterns = patterns or []

    def format(self, record):
        msg = super().format(record)
        for pattern in self.patterns:
            if pattern:
                msg = msg.replace(pattern, "********")
        return msg

    def set_patterns(self, patterns):
        self.patterns = patterns

class LogMessage(Message):
    def __init__(self, message: str) -> None:
        super().__init__()
        self.message = message

class TextualLogHandler(logging.Handler):
    def __init__(self, app):
        super().__init__()
        self.app = app

    def emit(self, record):
        try:
            msg = self.format(record)
            self.app.post_message(LogMessage(msg))
        except Exception:
            self.handleError(record)

class MenuButton(Static):
    def __init__(self, label: str, id: str):
        super().__init__(label, id=id, classes="menu-button")

    def on_click(self) -> None:
        # Map ID back to state
        state = self.id.replace("btn-header-", "")
        self.app.app_state = state

class RivenTUI(App):
    CSS_PATH = "riven_tui.tcss"
    BINDINGS = [
        ("ctrl+t", "toggle_debug", "Debug"),
    ]

    base_title = reactive("Riven TUI") 
    app_state: Literal["welcome", "dashboard", "search", "library", "calendar", "settings", "advanced", "logs"] = reactive("dashboard")
    current_calendar_date = reactive(datetime.now())
    calendar_filters = reactive({"movie": True, "episode": True, "show": True, "season": True})

    def __init__(self):
        super().__init__()
        self.settings = {}
        # Pre-load settings to get tokens for redaction
        try:
            with open("settings.json", "r") as f:
                self.settings = json.load(f)
        except:
            pass

        self.previous_logs = ""
        self.chafa_available = False
        self.post_message_debounce_timer = None 
        
        self.logger = logging.getLogger("Riven")
        self.tui_logger = logging.getLogger("Riven.TUI")
        self.tui_logger.propagate = True
        
        self.spinner = None
        self._clear_notification_timer = None
        self.refresh_delay_seconds = 3.0
        self.last_library_filters = {}
        self.library_selection: Dict[str, str] = {} # ID -> Title
        self.calendar_cache: List[dict] = [] 
        self.navigation_source: Literal["dashboard", "library", "search", "calendar"] = "dashboard"
        self.current_trending_page = 1
        self.tmdb_genres: Dict[int, str] = {}

    def log_message(self, message: str):
        self.tui_logger.info(message)

    def reconfigure_redaction(self):
        redact_patterns = []
        if self.settings.get("riven_key"):
            redact_patterns.append(self.settings["riven_key"])
        if self.settings.get("tmdb_bearer_token"):
            redact_patterns.append(self.settings["tmdb_bearer_token"])
        
        for handler in self.logger.handlers:
            if hasattr(handler, "formatter") and isinstance(handler.formatter, RedactingFormatter):
                handler.formatter.set_patterns(redact_patterns)

    @on(SettingsView.SettingsChanged)
    def on_settings_changed(self, message: SettingsView.SettingsChanged) -> None:
        # Merge new settings into memory to avoid losing TUI-specific keys like be_config
        self.settings.update(message.new_settings)
        self.reconfigure_redaction()
        self.log_message("Settings updated in memory (not saved to settings.json)")

    def on_load(self) -> None: 
        try:
            with open("settings.json", "r") as f:
                self.settings = json.load(f)
            self.reconfigure_redaction()
        except Exception as e:
            # We don't use tui_logger yet because logging isn't fully set up in on_load usually
            pass
        
        self.chafa_available = shutil.which("chafa") is not None
        
    def build_url(self, config_key: str) -> str:
        cfg = self.settings.get(config_key, {})
        protocol = cfg.get("protocol", "http")
        host = cfg.get("host", "localhost")
        port = cfg.get("port")
        
        if port:
            return f"{protocol}://{host}:{port}"
        return f"{protocol}://{host}"
        
    def action_toggle_debug(self) -> None:
        try:
            log_widget = self.query_one("#debug-log")
            log_widget.toggle_class("-visible")
        except NoMatches:
            pass

    @on(LogMessage)
    def on_log_message(self, message: LogMessage) -> None:
        try:
            log_widget = self.query_one("#debug-log", RichLog)
            if "-visible" in log_widget.classes:
                log_widget.write(message.message)
        except (NoMatches, AttributeError):
            pass

    @on(ToggleLibrarySelection)
    def on_toggle_library_selection(self, message: ToggleLibrarySelection) -> None:
        if message.item_id in self.library_selection:
            del self.library_selection[message.item_id]
        else:
            self.library_selection[message.item_id] = message.title
        
        self.tui_logger.debug(f"Selection changed: {len(self.library_selection)} items selected")

    def compose(self) -> ComposeResult:
        with Horizontal(id="header-bar"):
            yield MenuButton("Dashboard", id="btn-header-dashboard")
            yield MenuButton("Search", id="btn-header-search")
            yield MenuButton("Library", id="btn-header-library")
            yield MenuButton("Advanced", id="btn-header-advanced")
            yield MenuButton("Calendar", id="btn-header-calendar")
            yield MenuButton("Settings", id="btn-header-settings")
            yield MenuButton("Logs", id="btn-header-logs")
            yield Static(self.base_title, id="header-title")

        with Container(id="workspace"):
            with Vertical(id="dashboard-wrapper"):
                yield DashboardView(id="dashboard-view")
            yield Static("Welcome to Riven TUI! Click 'Search' to begin.", id="welcome-message")
            with Horizontal(id="main-area"):
                yield Sidebar(id="sidebar")
                with Vertical(id="content-wrapper"):
                    yield MainContent(id="content-area")
            
            yield SettingsView(id="settings-view")
            yield AdvancedView(id="advanced-view")
            yield LogsView(id="logs-view")

        yield RichLog(id="debug-log", highlight=True, markup=True, wrap=True, max_lines=1000)

        yield Footer()

    async def check_for_updates(self):
        """Checks GitHub for a newer version string."""
        import time
        url = f"https://raw.githubusercontent.com/subvhome/riven-tui/main/version.py?t={int(time.time())}"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    remote_content = resp.text
                    import re
                    match = re.search(r'VERSION\s*=\s*"([^"]+)"', remote_content)
                    if match:
                        remote_version = match.group(1)
                        
                        def version_tuple(v):
                            return tuple(map(int, (v.replace(",", ".").split("."))))
                        
                        try:
                            if version_tuple(remote_version) > version_tuple(VERSION):
                                self.push_screen(UpdateScreen(remote_version))
                                self.log_message(f"Update found: Local {VERSION} vs Remote {remote_version}")
                        except Exception as e:
                            self.log_message(f"Version comparison failed: {e}")
        except Exception as e:
            self.log_message(f"Update check failed: {e}")

    async def on_mount(self) -> None:
        # Setup unified logging in on_mount to ensure widgets are ready
        log_level_str = self.settings.get("log_level", "INFO").upper()
        log_level = getattr(logging, log_level_str, logging.INFO)
        self.logger.setLevel(log_level)
        
        # Sensitive tokens to redact
        redact_patterns = []
        if self.settings.get("riven_key"):
            redact_patterns.append(self.settings["riven_key"])
        if self.settings.get("tmdb_bearer_token"):
            redact_patterns.append(self.settings["tmdb_bearer_token"])

        if not self.logger.handlers:
            # File Handler
            file_handler = RotatingFileHandler('riven.log', maxBytes=5*1024*1024, backupCount=3)
            formatter = RedactingFormatter(
                '%(asctime)s - [%(name)s] - %(levelname)s - %(message)s',
                patterns=redact_patterns
            )
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
            
            # Textual Handler
            self.textual_handler = TextualLogHandler(self)
            self.textual_handler.setFormatter(formatter)
            self.logger.addHandler(self.textual_handler)

        self.tui_logger.debug("on_mount called")
        self.log_message("App mounted. Starting startup worker.")
        self.run_worker(self.perform_startup())

    async def perform_startup(self) -> None:
        self.tui_logger.debug("perform_startup worker started")
        import os
        import shutil
        if os.path.exists("y") and os.path.isdir("y"):
            try:
                shutil.rmtree("y")
                self.log_message("Auto-Cleanup: Removed redundant 'y/' folder.")
            except Exception as e:
                self.tui_logger.error(f"Auto-Cleanup Error (y/): {e}", exc_info=True)

        if "api_key" in self.settings and "riven_key" not in self.settings:
            self.settings["riven_key"] = self.settings.pop("api_key")
            self.log_message("Migrating api_key to riven_key in settings.json...")
            try:
                with open("settings.json", "w") as f:
                    json.dump(self.settings, f, indent=4)
            except Exception as e:
                self.tui_logger.error(f"Migration Error (Saving): {e}", exc_info=True)

        if not self.chafa_available:
            self.tui_logger.debug("Chafa not available, showing ChafaCheckScreen")
            if not await self.push_screen_wait(ChafaCheckScreen()):
                self.tui_logger.info("ChafaCheckScreen returned False, exiting")
                self.exit()
                return

        try:
            be_url = self.build_url("be_config")
            timeout = self.settings.get("request_timeout", 10.0)

            self.tui_logger.debug(f"Initializing API with BE URL: {be_url}, timeout: {timeout}")
            self.api = RivenAPI(be_url, timeout=timeout)
            self.log_message(f"API Initialized: BE='{be_url}'")
            
            # Fetch Genres for Search View
            self.tui_logger.debug("Fetching TMDB genres...")
            genre_map, err = await self.api.get_tmdb_genres(self.settings.get("tmdb_bearer_token"))
            if not err:
                self.tmdb_genres = genre_map
                self.log_message(f"TMDB Genres cached ({len(genre_map)} items)")
            else:
                self.tui_logger.error(f"Failed to fetch TMDB genres: {err}")

            self.tui_logger.debug("Initializing TitleSpinner and setting initial state")
            self.spinner = TitleSpinner(self, self.base_title) 
            self.app_state = "welcome" # Cycle state to force watcher to fire
            self.app_state = "dashboard" 
            self.tui_logger.debug("Startup worker completed, starting update check worker")
            self.run_worker(self.check_for_updates())
        except Exception as e:
            self.tui_logger.error(f"Config Error during startup: {e}", exc_info=True)
            self.notify(f"Config Error: {e}", severity="error")

    async def on_unmount(self) -> None:
        if hasattr(self, "api"):
            await self.api.shutdown()

    async def refresh_dashboard(self):
        if getattr(self, "_refreshing_dashboard", False):
            return
        self._refreshing_dashboard = True
        
        try:
            dashboard_view = self.query_one(DashboardView)
            riven_key = self.settings.get("riven_key")
            
            if not riven_key:
                return

            self.log_message("Dashboard: Starting refresh...")

            # Fetch stats, health, recently added, and trending in parallel
            stats_task = self.api.get_stats(riven_key)
            health_task = self.api.get_health(riven_key)
            recent_task = self.api.get_items(
                riven_key, 
                limit=10, 
                item_type=["movie", "show"], 
                sort="date_desc", 
                extended=False
            )
            trending_task = self.api.get_tmdb_trending(self.settings.get("tmdb_bearer_token"))
            services_task = self.api.get_services(riven_key)
            settings_task = self.api.get_settings(riven_key)
            
            self.log_message("Dashboard: Awaiting parallel API tasks...")
            try:
                results = await asyncio.gather(stats_task, health_task, recent_task, trending_task, services_task, settings_task, return_exceptions=True)
                self.tui_logger.debug(f"Dashboard: Raw API results: {results}")
                self.log_message(f"Dashboard: API tasks completed. Results count: {len(results)}")
            except Exception as e:
                self.tui_logger.error(f"Dashboard: Error in asyncio.gather: {e}", exc_info=True)
                return
            
            stats_resp = results[0] if not isinstance(results[0], Exception) else (None, str(results[0]))
            health_resp = results[1] if not isinstance(results[1], Exception) else (None, str(results[1]))
            recent_resp = results[2] if not isinstance(results[2], Exception) else (None, str(results[2]))
            trending_resp = results[3] if not isinstance(results[3], Exception) else (None, str(results[3]))
            services_resp = results[4] if not isinstance(results[4], Exception) else (None, str(results[4]))
            settings_resp = results[5] if not isinstance(results[5], Exception) else (None, str(results[5]))
            
            if any(isinstance(r, Exception) for r in results):
                for i, r in enumerate(results):
                    if isinstance(r, Exception):
                        self.tui_logger.error(f"Dashboard: Task {i} failed: {r}")

            stats_data = stats_resp[0] if stats_resp and stats_resp[0] else {}
            
            # Parse health response
            health_ok = False
            if health_resp and health_resp[0]:
                health_ok = health_resp[0].get("message") == "True"
                self.tui_logger.debug(f"Dashboard: Health status: {health_ok}")
            
            self.log_message("Dashboard: Updating UI components...")
            await dashboard_view.update_stats(stats_data, health_ok)
            
            # Update recently added
            if recent_resp and recent_resp[0]:
                recent_items = recent_resp[0].get("items", [])
                self.tui_logger.debug(f"Dashboard: Found {len(recent_items)} recent items")
                await dashboard_view.update_recently_added(recent_items)
                self.run_worker(self._fetch_recent_ratings(recent_items))
                
            # Update trending
            if trending_resp and trending_resp[0]:
                trending_items = trending_resp[0]
                self.tui_logger.debug(f"Dashboard: Found {len(trending_items)} trending items")
                # Show the list immediately (as unknown status)
                await dashboard_view.update_trending(trending_items)
                # Trigger background check for library status
                self.run_worker(self._check_trending_library_status(trending_items))

            # Update service pills
            if services_resp and services_resp[0] and settings_resp and settings_resp[0]:
                self.tui_logger.debug("Dashboard: Updating service pills")
                await dashboard_view.update_service_pills(services_resp[0], settings_resp[0])

            # Update distribution grid
            if stats_data.get("states"):
                self.tui_logger.debug(f"Dashboard: Updating states overview: {stats_data['states']}")
                await dashboard_view.update_states_overview(stats_data["states"])
            
            self.log_message("Dashboard: Refresh complete.")
        finally:
            self._refreshing_dashboard = False
            self.stop_spinner()

    def watch_app_state(self, new_state: Literal["welcome", "dashboard", "search", "library", "calendar", "settings", "advanced", "logs"]) -> None:
        self.tui_logger.debug(f"App state changing to: {new_state}")
        try:
            welcome_message = self.query_one("#welcome-message")
            main_area = self.query_one("#main-area")
            sidebar = self.query_one(Sidebar)
            main_content = self.query_one(MainContent)
            settings_view = self.query_one(SettingsView)
            dashboard_view = self.query_one(DashboardView)
            dashboard_wrapper = self.query_one("#dashboard-wrapper")
            advanced_view = self.query_one(AdvancedView)
            logs_view = self.query_one("#logs-view")
        except NoMatches:
            return

        welcome_message.display = False
        main_area.display = False
        sidebar.display = False
        main_content.display = False
        settings_view.display = False
        dashboard_view.display = False
        dashboard_wrapper.display = False
        advanced_view.display = False
        logs_view.display = False

        # Reset MainContent visibility state
        main_content.reset_view()
        
        # New Search Grid Visibility Reset
        main_content.query_one("#centered-search-container").add_class("hidden")
        main_content.query_one("#search-grid-scroll").add_class("hidden")
        main_content.query_one("#main-content-scroll-area").remove_class("hidden")

        # Update Tab Classes - Clean and precise
        for btn in self.query(".menu-button"):
            btn.remove_class("-active")
        
        try:
            target_id = f"#btn-header-{new_state}"
            self.query_one(target_id).add_class("-active")
        except NoMatches:
            pass

        if new_state == "welcome":
            welcome_message.display = True
        elif new_state == "dashboard":
            dashboard_view.display = True
            dashboard_wrapper.display = True
            self.run_worker(self.refresh_dashboard())
        elif new_state == "advanced":
            advanced_view.display = True
        elif new_state == "search":
            main_area.display = True
            sidebar.display = False # Hide sidebar for full width
            main_content.display = True 
            
            # Switch to Grid Mode
            main_content.query_one("#main-content-scroll-area").add_class("hidden")
            main_content.query_one("#centered-search-container").remove_class("hidden")
            main_content.query_one("#search-grid-scroll").remove_class("hidden")
            
            # Focus Input
            try:
                self.query_one("#grid-search-input").focus()
            except NoMatches:
                pass

        elif new_state == "library":
            main_area.display = True
            sidebar.display = True
            sidebar.show_library_filters() 
            main_content.display = True
            self.run_worker(self.show_library_items())
        elif new_state == "calendar":
            main_area.display = True
            sidebar.display = True 
            sidebar.show_calendar_summary() 
            main_content.display = True
            main_content.query_one("#main-content-container").remove_children()
            self.run_worker(self.show_calendar(refresh_cache=True))
        elif new_state == "settings":
            settings_view.display = True
            sidebar.display = True
            sidebar.show_blank()
            main_area.display = True
            if not settings_view.settings_data:
                self.run_worker(settings_view.load_data())
        elif new_state == "logs":
            logs_view.display = True
            # Full width, no sidebar
            main_area.display = False
            sidebar.display = False
            self.run_worker(logs_view.update_logs(refresh_all=True))

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
        self.tui_logger.debug(f"Starting spinner: {message}")
        if self._clear_notification_timer:
            self._clear_notification_timer.stop()
            self._clear_notification_timer = None
        if self.spinner is not None:
            await self.spinner.start(message, interval)

    def stop_spinner(self):
        self.tui_logger.debug("Stopping spinner")
        if self.spinner is not None:
            self.spinner.stop()

    async def on_resize(self, event) -> None: 
        try:
            main_content = self.query_one(MainContent)
        except NoMatches:
            return
        
        # Handle responsive stacking for media details
        try:
            detail_layout = main_content.query_one(".media-detail-layout")
            if event.size.width < 100:
                detail_layout.add_class("-stacked")
                main_content.add_class("-stacked")
            else:
                detail_layout.remove_class("-stacked")
                main_content.remove_class("-stacked")
        except NoMatches:
            pass

        try:
            _ = main_content.query_one("#poster-display", Static)
            if self.post_message_debounce_timer:
                self.post_message_debounce_timer.stop()
            self.post_message_debounce_timer = self.set_timer(0.2, lambda: self.post_message(RefreshPoster()))
        except NoMatches:
            pass

    async def on_refresh_poster(self, message: RefreshPoster) -> None: 
        main_content = self.query_one(MainContent)
        try:
            poster_widget = main_content.query_one("#poster-display", Static)
        except NoMatches:
            return 

        # Determine if we are stacked
        is_stacked = False
        try:
            detail_layout = main_content.query_one(".media-detail-layout")
            is_stacked = detail_layout.has_class("-stacked")
        except NoMatches:
            pass

        # Try to measure the actual action column if it exists (most accurate)
        target_width = None
        try:
            action_col = main_content.query_one(".media-action-column")
            if action_col.size.width > 0:
                # Subtract padding (2) + border (1) + safety (3) = 6
                target_width = max(10, action_col.size.width - 6)
        except NoMatches:
            pass

        if target_width is None:
            # Fallback calculation
            main_content_width = main_content.size.width
            if not is_stacked and main_content_width > 100:
                # CSS defines action column as 75fr (75%)
                target_width = max(10, int(main_content_width * 0.75) - 14)
            else:
                target_width = max(10, main_content_width - 14)

        # Apply Max Width Setting
        chafa_max_width = self.settings.get("chafa_max_width", 50)
        if chafa_max_width > 0:
            target_width = min(target_width, chafa_max_width)

        # Height for 2:3 aspect ratio
        target_height = int(target_width * 0.75)

        # Only refresh if the difference is significant
        if (
            main_content.last_chafa_width is None
            or abs(target_width - main_content.last_chafa_width) > 2
        ):
            tmdb_data = main_content.tmdb_details
            if tmdb_data and tmdb_data.get("poster_path"):
                poster_url = f"https://image.tmdb.org/t/p/w1280{tmdb_data['poster_path']}"
                poster_art, error = await self.api.get_poster_chafa(poster_url, width=target_width, height=target_height)
                if not error:
                    poster_widget.update(Text.from_ansi(poster_art))
                    main_content.last_chafa_width = target_width

    @on(Input.Submitted, "#grid-search-input")
    async def on_grid_search_submitted(self, event: Input.Submitted):
        query = event.value.strip()
        if query:
            # We can just manually call handle_search with a faux message
            await self.handle_search(SearchSubmitted(query=query))

    @on(SearchSubmitted)
    async def handle_search(self, message: SearchSubmitted):
        self.log_message(f"SearchSubmitted received: {message.query}")
        self.app_state = "search" 
        
        main_content = self.query_one(MainContent)
        grid_container = main_content.query_one("#search-grid-container")
        
        # Reset visibility - ensure we are in grid mode
        main_content.query_one("#main-content-scroll-area").add_class("hidden")
        main_content.query_one("#centered-search-container").remove_class("hidden")
        main_content.query_one("#search-grid-scroll").remove_class("hidden")
        main_content.query_one("#btn-back-to-actions").add_class("hidden")

        await grid_container.query("*").remove() 

        await self.start_spinner(f"Searching for '{message.query}'")
        results, error = await self.api.search_tmdb(message.query, self.settings.get("tmdb_bearer_token"))
        
        if error:
            self.stop_spinner()
            self.log_message(f"TMDB Search Error: {error}")
            self.notify(f"TMDB Error: {error}", severity="error")
            return

        self.log_message(f"TMDB found {len(results)} raw results.")
        results.sort(key=lambda x: x.get('popularity', 0) or 0, reverse=True)
        results = results[:20] # Keep top 20

        # Fetch full details in parallel for taglines and genres
        async def fetch_item_details(item):
            tmdb_token = self.settings.get("tmdb_bearer_token")
            riven_key = self.settings.get("riven_key")
            
            # 1. Fetch TMDB Details
            details, _ = await self.api.get_tmdb_details(item['media_type'], item['id'], tmdb_token)
            if details:
                item.update(details)
            
            # 2. Check Library State
            # Map 'tv' to 'tv' or 'movie' to 'movie' for Riven
            riven_media_type = "movie" if item['media_type'] == "movie" else "tv"
            
            # For TV, try to get TVDB ID if missing
            lookup_id = item['id']
            if riven_media_type == "tv":
                lookup_id = item.get("external_ids", {}).get("tvdb_id") or item['id']

            lib_item = await self.api.get_item_by_id(riven_media_type, str(lookup_id), riven_key)
            if lib_item:
                item["state"] = lib_item.get("state", "Unknown")
                item["riven_id"] = lib_item.get("id")
            
            return item

        detailed_results = await asyncio.gather(*(fetch_item_details(r) for r in results))
        
        self.stop_spinner()
        self.log_message(f"Mounted {len(detailed_results)} tiles to grid.")
        
        if not detailed_results:
            await grid_container.mount(Label("No results found."))
        else:
            first_tile = None
            for item in detailed_results:
                tile = SearchGridTile(item, self.api)
                if not first_tile:
                    first_tile = tile
                await grid_container.mount(tile)
            
            if first_tile:
                first_tile.focus()

    async def _render_poster(self, container: Container, tmdb_data: dict, width_hint: Optional[int] = None):
        if self.chafa_available and tmdb_data.get("poster_path"):
            main_content = self.query_one(MainContent)
            
            # If no width hint is provided (initial load), mount an empty placeholder
            # The 100ms timer in show_item_actions will trigger a precise refresh.
            if not width_hint:
                await container.mount(Static(id="poster-display"))
                main_content.last_chafa_width = None
                return

            poster_url = f"https://image.tmdb.org/t/p/w1280{tmdb_data['poster_path']}"
            chafa_target_width = width_hint

            chafa_max_width = self.settings.get("chafa_max_width", 50)
            if chafa_max_width > 0:
                chafa_target_width = min(chafa_target_width, chafa_max_width)
            
            poster_art, error = await self.api.get_poster_chafa(poster_url, width=chafa_target_width)
            if not error:
                await container.mount(Static(Text.from_ansi(poster_art), id="poster-display"))
                main_content.last_chafa_width = chafa_target_width

    async def show_item_actions(self, target_poster_width: Optional[int] = None):
        main_content = self.query_one(MainContent)
        main_content.add_class("media-details-active")
        container = main_content.query_one("#main-content-container")

        # Reset visibility
        container.remove_class("hidden")
        main_content.query_one("#library-list").add_class("hidden")
        main_content.query_one("#main-content-json-container").add_class("hidden")
        main_content.query_one("#btn-back-to-actions").add_class("hidden")

        await container.query("*").remove()
        main_content.last_chafa_width = None 
        tmdb_data = main_content.tmdb_details
        riven_data = main_content.item_details
        search_item_data = main_content.item_data 
        if not tmdb_data:
            return

        # Prepare Data
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

        # Create Split Layout
        split_layout = Horizontal(classes="media-detail-layout")
        await container.mount(split_layout)
        
        info_col = Vertical(classes="media-info-column")
        action_col = Vertical(classes="media-action-column")
        await split_layout.mount(info_col)
        await split_layout.mount(action_col)

        # 1. Populate Info Column (Left)
        await info_col.mount(Static(f"[bold]{title}[/bold]", classes="media-title"))
        if tagline:
            await info_col.mount(Static(f"[italic]{tagline}[/italic]", classes="media-tagline"))
        
        metadata_items = [year]
        if search_item_data and search_item_data.get("media_type") == "movie" and runtime_movie:
            metadata_items.append(f"{runtime_movie} mins")
        elif search_item_data and search_item_data.get("media_type") == "tv" and episode_run_time:
            metadata_items.append(episode_run_time)
        if languages_spoken:
            metadata_items.append(languages_spoken)
        if status:
            metadata_items.append(status)
        if riven_data:
            metadata_items.append(f"[bold]{riven_data.get('state', 'Unknown').title()}[/]")
            
        if metadata_items:
            await info_col.mount(Static(" • ".join(filter(None, metadata_items)), classes="media-metadata"))
        
        if genres:
            await info_col.mount(Static(f"Genres: {genres}", classes="media-genres"))
        if description:
            await info_col.mount(Static(description, classes="media-overview"))

        # 2. Populate Action Column (Right)
        action_buttons = []
        if riven_data:
            action_buttons.extend([
                Button("Delete", id="btn-delete", variant="error"),
                Button("Reset", id="btn-reset", variant="warning"),
                Button("Retry", id="btn-retry", variant="primary"),
            ])
        
        action_buttons.append(Button("Manual Scrape", id="btn-manual-scrape", variant="success"))
        if not riven_data:
            action_buttons.append(Button("Request", id="btn-add", variant="success"))
        
        action_buttons.append(Button("Back", id="btn-back-to-library", variant="primary"))
        action_buttons.append(Button("JSON", id="btn-print-json"))
        
        await action_col.mount(Horizontal(*action_buttons, classes="media-button-bar"))
        
        # Render poster in the action column
        await self._render_poster(action_col, tmdb_data, width_hint=target_poster_width)
        
        # Force a refresh to correct any layout shifts
        self.set_timer(0.1, lambda: self.post_message(RefreshPoster()))

    @on(CalendarItemSelected)
    async def on_calendar_item_selected(self, message: CalendarItemSelected) -> None:
        self.navigation_source = "calendar"
        main_content = self.query_one(MainContent)
        cal_item = message.item_data
        
        media_type = cal_item.get("item_type")
        if media_type in ("show", "season", "episode"):
            media_type = "tv"
        
        tmdb_id = cal_item.get("tmdb_id")
        tvdb_id = cal_item.get("tvdb_id") or cal_item.get("tvdbId")

        # If it's a TV item, ensure we have the SHOW's TMDB ID.
        if media_type == "tv" and tvdb_id:
            # Resolve Show TMDB ID via TVDB ID
            found_id, error = await self.api.find_tmdb_id(str(tvdb_id), "tvdb_id", self.settings.get("tmdb_bearer_token"))
            if found_id:
                tmdb_id = found_id
        
        if not tmdb_id or not media_type:
            self.notify("Cannot open item: missing TMDB ID or type", severity="error")
            return

        main_content.item_data = {
            "id": tmdb_id,
            "media_type": media_type,
            "title": cal_item.get("title") or cal_item.get("show_title")
        }
        
        await self._refresh_current_item_data_and_ui(delay=0)

    @on(SearchGridTile.Selected)
    async def on_search_grid_tile_selected(self, message: SearchGridTile.Selected) -> None:
        # Reuse dashboard item click logic for consistency
        # Wrap it in a faux event-like object or call logic directly?
        # Actually, let's just copy the logic or call a shared method.
        # Calling shared method logic is cleaner.
        
        item = message.item_data
        tmdb_id = item.get("id")
        media_type = item.get("media_type", "movie")
        
        await self._open_media_card(tmdb_id, media_type)

    async def _open_media_card(self, tmdb_id: int, media_type: str):
        if not tmdb_id:
            self.notify("Cannot open item: missing TMDB ID", severity="error")
            return

        # Fetch details and show modal
        await self.start_spinner("Fetching details...")
        tmdb_details, error = await self.api.get_tmdb_details(media_type, tmdb_id, self.settings.get("tmdb_bearer_token"))
        if error:
            self.stop_spinner()
            self.notify(f"TMDB Error: {error}", severity="error")
            return
            
        riven_media_type = "tv" if media_type == "tv" else "movie"
        # For movies, Riven ID is TMDB ID. For shows, we might need TVDB ID.
        riven_id_to_check = tmdb_details.get("external_ids", {}).get("tvdb_id") if media_type == "tv" else tmdb_id
        
        riven_details = None
        if riven_id_to_check:
            riven_details = await self.api.get_item_by_id(riven_media_type, str(riven_id_to_check), self.settings.get("riven_key"))
            
        self.stop_spinner()
        
        self.push_screen(
            MediaCardScreen(tmdb_details, riven_details, media_type, self.api, self.settings, self.chafa_available),
            callback=self.handle_modal_result
        )

    async def handle_modal_result(self, result: any) -> None:
        if isinstance(result, dict) and result.get("action") == "trigger_manual_scrape":
            main_content = self.query_one(MainContent)
            main_content.item_data = result.get("item_data")
            main_content.tmdb_details = result.get("tmdb_details")
            main_content.item_details = result.get("item_details")
            self.run_worker(self._run_manual_scrape())

    @on(DashboardView.DashboardItem.Clicked)
    async def on_dashboard_item_clicked(self, message: DashboardView.DashboardItem.Clicked) -> None:
        self.navigation_source = "dashboard"
        item = message.item_data
        source = message.source
        
        tmdb_id = None
        media_type = None
        
        if source == "library":
            tmdb_id = await self.api.resolve_tmdb_id(item, self.settings.get("tmdb_bearer_token"))
            media_type = item.get("type", "movie")
            if media_type == "show":
                media_type = "tv"
        else: # trending
            tmdb_id = item.get("id")
            media_type = item.get("media_type", "movie")

        await self._open_media_card(tmdb_id, media_type)

    @on(DashboardView.DashboardItem.QuickAdd)
    async def on_dashboard_quick_add(self, message: DashboardView.DashboardItem.QuickAdd) -> None:
        item = message.item_data
        media_type = item.get("media_type", "movie")
        tmdb_id = item.get("id")
        title = item.get("title") or item.get("name")
        
        riven_key = self.settings.get("riven_key")
        tmdb_token = self.settings.get("tmdb_bearer_token")
        
        self.notify(f"Adding '{title}' to library...", severity="information")
        
        target_id = str(tmdb_id)
        id_type = "tmdb_ids"
        
        if media_type == "tv":
            # For TV, we MUST use TVDB ID per user request
            tmdb_details, err = await self.api.get_tmdb_details("tv", tmdb_id, tmdb_token)
            if tmdb_details:
                tvdb_id = tmdb_details.get("external_ids", {}).get("tvdb_id")
                if tvdb_id:
                    target_id = str(tvdb_id)
                    id_type = "tvdb_ids"
                else:
                    self.notify(f"Could not find TVDB ID for '{title}'. Cannot add.", severity="error")
                    return
            else:
                self.notify(f"Failed to fetch TV details: {err}", severity="error")
                return

        # Map 'tv' to 'tv' for Riven add endpoint
        riven_media_type = "movie" if media_type == "movie" else "tv"
        
        success, response = await self.api.add_item(riven_media_type, id_type, target_id, riven_key)
        if success:
            self.notify(f"'{title}' added successfully!", severity="success")
            # Refresh the dashboard to update the [+] button status
            self.run_worker(self.refresh_dashboard())
        else:
            self.notify(f"Failed to add '{title}': {response}", severity="error")

    async def _fetch_recent_ratings(self, items: list):
        """Background task to fetch ratings for recently added items."""
        dashboard_view = self.query_one(DashboardView)
        tmdb_token = self.settings.get("tmdb_bearer_token")
        ratings_map = {}
        
        async def fetch_item_rating(item):
            # Key to use for dashboard mapping
            tmdb_id_raw = item.get("tmdb_id") or (item.get("parent_ids") or {}).get("tmdb_id")
            tvdb_id_raw = item.get("tvdb_id") or (item.get("parent_ids") or {}).get("tvdb_id")
            item_key = str(tmdb_id_raw or tvdb_id_raw or "")
            
            if not item_key:
                return None, 0

            media_type = item.get("type", "movie")
            resolved_tmdb_id = await self.api.resolve_tmdb_id(item, tmdb_token)

            # 3. Once we have a TMDB ID, fetch the official rating from TMDB
            if resolved_tmdb_id:
                details, err = await self.api.get_tmdb_details("tv" if media_type == "show" else "movie", resolved_tmdb_id, tmdb_token)
                if details:
                    return item_key, details.get("vote_average", 0)
            
            return None, 0

        results = await asyncio.gather(*(fetch_item_rating(i) for i in items))
        for key, rating in results:
            if key:
                ratings_map[key] = rating
        
        if ratings_map:
            await dashboard_view.update_recently_added(items, ratings=ratings_map)

    async def _check_trending_library_status(self, trending_items: list):
        """Background task to check if trending items are in Riven library."""
        dashboard_view = self.query_one(DashboardView)
        riven_key = self.settings.get("riven_key")
        status_map = {}
        
        # Limit to top 10 to avoid too many requests
        check_items = trending_items[:10]
        
        async def check_item(item):
            m_type = item.get("media_type", "movie")
            tmdb_id = item.get("id")
            
            # For TV, we need to resolve TVDB ID first
            id_to_check = str(tmdb_id)
            if m_type == "tv":
                tmdb_details, _ = await self.api.get_tmdb_details("tv", tmdb_id, self.settings.get("tmdb_bearer_token"))
                if tmdb_details:
                    id_to_check = tmdb_details.get("external_ids", {}).get("tvdb_id")
            
            if not id_to_check:
                return str(tmdb_id), False
                
            # Check Riven
            riven_type = "movie" if m_type == "movie" else "tv"
            lib_item = await self.api.get_item_by_id(riven_type, str(id_to_check), riven_key)
            return str(tmdb_id), lib_item is not None

        results = await asyncio.gather(*(check_item(i) for i in check_items))
        for tid, exists in results:
            status_map[tid] = exists
            
        await dashboard_view.update_trending(trending_items, library_status=status_map)

    @on(ListView.Selected, "#sidebar-list")
    async def on_list_view_selected(self, event: ListView.Selected) -> None: 
        self.navigation_source = "search"
        main_content = self.query_one(MainContent)
        selected_item_label = event.item.name
        if selected_item_label == "Logs":
            await self.show_initial_logs()
            return
        if selected_item_label == "Settings":
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
            self.notify(f"TMDB Error during repull: {error}", severity="error")
            main_content.tmdb_details = None 
            main_content.item_details = None 
            self.stop_spinner()
            await self.show_item_actions()
            return
        main_content.tmdb_details = tmdb_details
        # Robust mapping: If not movie, it's a TV/Show category for Riven
        riven_media_type = "movie" if media_type == "movie" else "tv"
        
        # Prioritize preserved riven_id, fallback to resolving from TMDB details
        riven_id_to_check = tmdb_search_result.get("riven_id")
        if not riven_id_to_check:
            riven_id_to_check = tmdb_details.get("external_ids", {}).get("tvdb_id") if media_type == "tv" else tmdb_id
            
        if not riven_id_to_check:
            main_content.item_details = None
        else:
            main_content.item_details = await self.api.get_item_by_id(riven_media_type, str(riven_id_to_check), self.settings.get("riven_key"))
        self.stop_spinner() 
        await self.show_item_actions() 

    async def show_library_items(self, limit: int = 20, page: int = 1, sort: str = "date_desc", item_type: str | None = None, search: str | None = None, states: List[str] | None = None, refresh_cache: bool = False) -> None:
        self.last_library_filters = {
            "limit": limit,
            "page": page,
            "sort": sort,
            "item_type": item_type,
            "search": search,
            "states": states,
        }
        main_content = self.query_one(MainContent)
        container = main_content.query_one("#main-content-container")
        lib_list = main_content.query_one("#library-list")
        
        await container.query("*").remove() 
        lib_list.clear()
        
        await self.start_spinner("Fetching library...")
        
        riven_key = self.settings.get("riven_key")
        
        # Determine the types to send to the API.
        api_item_type = item_type if item_type is not None else ["movie", "show"]
            
        # Call the API with all filters, limit, and page
        resp, err = await self.api.get_items(
            riven_key, 
            limit=limit, 
            page=page, 
            sort=sort, 
            search=search, 
            item_type=api_item_type, 
            states=states,
            extended=False,
        )
        
        self.stop_spinner()

        if err:
            self.notify(f"API Error: {err}", severity="error")
            return

        self.tui_logger.debug(f"Library API response meta: total_items={resp.get('total_items')}, total_pages={resp.get('total_pages')}")
        items = resp.get("items", [])
        total_count = resp.get("total_items", resp.get("total", 0))
        total_pages = resp.get("total_pages", math.ceil(total_count / limit) if limit > 0 else 1)

        if items:
            await self.start_spinner("Enriching library data...")
            # Parallel fetch TMDB details for all items to get ratings/genres/taglines
            async def enrich_item(item):
                try:
                    # 1. Identify IDs
                    # Riven internal list ID
                    item["riven_id"] = str(item.get("id"))
                    
                    m_type = item.get("type", "movie")
                    tmdb_m_type = "movie" if m_type == "movie" else "tv"
                    
                    # lookup_id is what Riven detail API expects (TMDB for movie, TVDB for show)
                    lookup_id = item.get("tmdb_id") if m_type == "movie" else (item.get("tvdb_id") or (item.get("parent_ids") or {}).get("tvdb_id"))
                    if not lookup_id and m_type == "show":
                        lookup_id = item.get("id")
                    
                    item["lookup_id"] = str(lookup_id) if lookup_id else None
                    
                    # 2. Identify TMDB ID for metadata enrichment
                    tmdb_token = self.settings.get("tmdb_bearer_token")
                    tmdb_id = await self.api.resolve_tmdb_id(item, tmdb_token)

                    # 3. Enrich
                    if tmdb_id:
                        details, _ = await self.api.get_tmdb_details(tmdb_m_type, tmdb_id, tmdb_token)
                        if details:
                            # Preserve Riven-specific fields that TMDB might overwrite or lack
                            p_title = item.get("parent_title")
                            # Preserve all variations of S/E keys and flags
                            preserved_vals = {
                                k: item.get(k) for k in [
                                    "season_number", "episode_number", 
                                    "seasonNumber", "episodeNumber",
                                    "season", "episode", "is_anime"
                                ] if item.get(k) is not None
                            }
                            
                            # Only take "enrichment" fields from TMDB
                            enrichment_fields = [
                                "tagline", "genres", "vote_average", "vote_count", 
                                "overview", "popularity", "content_rating", "original_language"
                            ]
                            for field in enrichment_fields:
                                if field in details:
                                    item[field] = details[field]
                            
                            # Restore preserved fields
                            if p_title: item["parent_title"] = p_title
                            for k, v in preserved_vals.items():
                                item[k] = v
                            
                            # Use TMDB poster if Riven doesn't provide one
                            if not item.get("poster_path") and details.get("poster_path"):
                                item["poster_path"] = details["poster_path"]
                            
                            item["tmdb_id"] = tmdb_id
                except Exception as e:
                    self.tui_logger.error(f"Failed to enrich library item: {e}")
                
                return item

            results = await asyncio.gather(*(enrich_item(i) for i in items), return_exceptions=True)
            # Filter out any actual Exception objects that might have bubbled up
            items = [r for r in results if isinstance(r, dict)]
            self.stop_spinner()

        if not items:
            container.remove_class("hidden")
            lib_list.add_class("hidden")
            await container.mount(Static("No library items found matching your filters.", id="empty-library-msg"))
        else:
            container.add_class("hidden")
            lib_list.remove_class("hidden")
            for item in items:
                is_selected = str(item.get("id")) in self.library_selection
                await lib_list.append(LibraryItemCard(item, initial_selected=is_selected))
                
        # Update Pagination Controls
        sidebar = self.query_one(Sidebar)
        sidebar.update_pagination(page, total_pages)

    @on(ListView.Selected, "#library-list")
    async def on_library_item_clicked(self, event: ListView.Selected) -> None: 
        self.navigation_source = "library"
        item_data = event.item.item_data
        media_type = item_data.get("type")
        
        tmdb_id = await self.api.resolve_tmdb_id(item_data, self.settings.get("tmdb_bearer_token"))
        
        if not tmdb_id:
            self.notify(f"No TMDB ID found for '{item_data.get('title')}'. Cannot fetch details.", severity="warning")
            return
            
        main_content = self.query_one(MainContent)
        main_content.item_data = {
            "id": tmdb_id,
            "media_type": "movie" if media_type == "movie" else "tv",
            "riven_id": item_data.get("lookup_id") or item_data.get("riven_id") or item_data.get("id")
        }
        await self._refresh_current_item_data_and_ui(delay=0)

    @on(Button.Pressed, "#btn-back-to-library")
    async def handle_back_to_library(self):
        if self.navigation_source == "dashboard":
            # Manually trigger the watch logic to restore visibility
            self.watch_app_state("dashboard")
        elif self.navigation_source == "library":
            if self.last_library_filters:
                # Limit might have changed, but page is no longer tracked
                await self.show_library_items(**self.last_library_filters)
            else:
                await self.show_library_items()
        elif self.navigation_source == "search":
            self.app_state = "search"
        elif self.navigation_source == "calendar":
            self.app_state = "calendar"
            await self.show_calendar()
        else:
            self.app_state = "library"

    async def show_initial_logs(self):
        url, error = await self.api.upload_logs(self.settings.get("riven_key"))
        if error:
            self.notify(f"Error uploading logs: {error}", severity="error")
            return
        logs, error = await self.api.get_logs_from_url(url)
        if error:
            self.notify(f"Error fetching logs: {error}", severity="error")
            return
        self.previous_logs = logs
        limit = self.settings.get("log_display_limit", 20)
        log_lines = logs.splitlines()
        display_logs = "\n".join(log_lines[-limit:])
        main_content = self.query_one(MainContent)
        await main_content.display_logs(display_logs)

    @on(Button.Pressed, "#btn-prev-page")
    async def on_prev_page_click(self, event: Button.Pressed):
        event.stop()
        if self.last_library_filters:
            current_page = self.last_library_filters.get("page", 1)
            if current_page > 1:
                # Update filters and reload directly
                self.last_library_filters["page"] = current_page - 1
                await self.show_library_items(**self.last_library_filters)

    @on(Button.Pressed, "#btn-next-page")
    async def on_next_page_click(self, event: Button.Pressed):
        event.stop()
        if self.last_library_filters:
            current_page = self.last_library_filters.get("page", 1)
            # Update filters and reload directly
            self.last_library_filters["page"] = current_page + 1
            await self.show_library_items(**self.last_library_filters)

    @on(MonthChanged)
    async def on_month_changed(self, event: MonthChanged):
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
            riven_key = self.settings.get("riven_key")
            resp, err = await self.api.get_calendar(riven_key)
            if err:
                self.notify(f"Error fetching calendar: {err}", severity="error")
                self.stop_spinner()
                return
            
            self.tui_logger.debug(f"Calendar raw response: {resp}")
            
            if isinstance(resp, dict) and "data" in resp:
                self.calendar_cache = list(resp["data"].values())
            else:
                self.calendar_cache = []
            self.stop_spinner()
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
        active_days = set()
        for item in monthly_items:
            date_key = item["_dt"].strftime("%a, %B %d")
            if date_key not in grouped_items:
                grouped_items[date_key] = []
            grouped_items[date_key].append(item)
            active_days.add(item["_dt"].day)
            
        sidebar = self.query_one(Sidebar)
        await sidebar.update_calendar_grid(year, month, active_days)

        await container.query("*").remove()
        await container.mount(CalendarHeader(year, month))
        legend_row = Horizontal(id="calendar-legend-row")
        await container.mount(legend_row)
        filters = [("movie", "Movies"), ("episode", "Episodes"), ("show", "Shows"), ("season", "Seasons")]
        for f_type, label in filters:
            pill = FilterPill(label, value=self.calendar_filters[f_type], filter_type=f_type)
            await legend_row.mount(pill)
        if not monthly_items:
            await container.mount(Static(f"No items found for {calendar.month_name[month]} {year}.", id="calendar-no-items"))
        else:
            target_day_num = None
            today = datetime.now()
            
            for date_str, items in grouped_items.items():
                day_num = items[0]["_dt"].day
                day_group = Vertical(classes="calendar-day-group", id=f"day-group-{day_num}")
                await container.mount(day_group)
                header_row = Horizontal(classes="calendar-day-header")
                await day_group.mount(header_row)
                await header_row.mount(Label(date_str, classes="calendar-date-label")),
                await header_row.mount(Label(f"{len(items)} item{'s' if len(items) > 1 else ''}", classes="calendar-count-label")),
                for item in items:
                    await day_group.mount(CalendarItemCard(item))
                
                # Logic to find the best day to scroll to
                # We want the first day that is >= today
                if target_day_num is None:
                    item_dt = items[0]["_dt"]
                    if item_dt.year == today.year and item_dt.month == today.month:
                        if item_dt.day >= today.day:
                            target_day_num = day_num
                    elif item_dt.year > today.year or (item_dt.year == today.year and item_dt.month > today.month):
                        # Future month/year, pick the first available day
                        target_day_num = day_num

            # Perform the jump
            if target_day_num is not None:
                def jump_to_day():
                    try:
                        target_widget = container.query_one(f"#day-group-{target_day_num}")
                        target_widget.scroll_visible(top=True, animate=False)
                    except NoMatches:
                        pass
                self.set_timer(0.1, jump_to_day)

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

    @on(Button.Pressed, "#btn-refresh-logs")
    async def refresh_logs(self):
        url, error = await self.api.upload_logs(self.settings.get("riven_key"))
        if error:
            self.notify(f"Error uploading logs: {error}", severity="error")
            return
        logs, error = await self.api.get_logs_from_url(url)
        if error:
            self.notify(f"Error fetching logs: {error}", severity="error")
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
        else:
            self.notify("No new logs.")

    @on(Button.Pressed, "#btn-print-json")
    async def handle_print_json(self):
        main_content = self.query_one(MainContent)
        tmdb_details = main_content.tmdb_details
        item_data = main_content.item_data
        
        if tmdb_details and item_data:
            # Robust mapping
            media_type = "movie" if item_data.get("media_type") == "movie" else "tv"
            # Use the ID Riven expects (preserved in riven_id)
            external_id = item_data.get("riven_id")
            
            if not external_id:
                tmdb_id = tmdb_details.get("id")
                tvdb_id = tmdb_details.get("external_ids", {}).get("tvdb_id")
                external_id = str(tvdb_id) if media_type == "tv" and tvdb_id else str(tmdb_id)
            
            await self.start_spinner("Fetching extended Riven data...")
            extended_data = await self.api.get_item_by_id(media_type, str(external_id), self.settings.get("riven_key"), extended=True)
            self.stop_spinner()
            
            data = extended_data or main_content.item_details or {"info": "Item not in Riven library"}
        else:
            data = {"info": "No TMDB details available"}
            
        await main_content.display_json(data)

    @on(Button.Pressed, "#btn-delete")
    async def handle_delete(self):
        main_content = self.query_one(MainContent)
        item_id = main_content.item_details.get("id")
        if not item_id: return
        success, response = await self.api.delete_item(item_id, self.settings.get("riven_key"))
        if success:
            self.notify(f"Item deleted.", severity="information")
            main_content.item_details = None 
            await self._refresh_current_item_data_and_ui(delay=self.refresh_delay_seconds) 
        else:
            self.notify("Failed to delete item.", severity="error")

    @on(Button.Pressed, "#btn-reset")
    async def handle_reset(self):
        main_content = self.query_one(MainContent)
        item_id = main_content.item_details.get("id")
        if not item_id: return
        success, response = await self.api.reset_item(item_id, self.settings.get("riven_key"))
        if success:
            self.notify("Item reset successfully.", severity="information")
            await self._refresh_current_item_data_and_ui(delay=self.refresh_delay_seconds) 
        else:
            self.notify("Failed to reset item.", severity="error")

    @on(Button.Pressed, "#btn-retry")
    async def handle_retry(self):
        main_content = self.query_one(MainContent)
        item_id = main_content.item_details.get("id")
        if not item_id: return
        success, response = await self.api.retry_item(item_id, self.settings.get("riven_key"))
        if success:
            self.notify("Item sent for retry.", severity="information")
            await self._refresh_current_item_data_and_ui(delay=self.refresh_delay_seconds) 
        else:
            self.notify("Failed to retry item.", severity="error")

    @on(Button.Pressed, "#btn-manual-scrape")
    def handle_manual_scrape_button(self):
        self.run_worker(self._run_manual_scrape)

    async def _run_manual_scrape(self):
        main_content = self.query_one(MainContent)
        if not main_content.tmdb_details:
            return
        tmdb_id = main_content.tmdb_details.get("id")
        riven_item_id = main_content.item_details.get("id") if main_content.item_details else None
        media_type = main_content.item_data.get("media_type")
        if not media_type:
            return
        tvdb_id_for_scrape = None
        if media_type == "tv" and not riven_item_id:
            tvdb_id_for_scrape = main_content.tmdb_details.get("external_ids", {}).get("tvdb_id")
            if not tvdb_id_for_scrape:
                self.notify(f"Could not find TVDB ID for {main_content.tmdb_details.get('name')} to scrape.", severity="error")
                return
        await self.start_spinner("Discovering streams...")
        log_screen = ScrapeLogScreen(media_type, tmdb_id, self.settings.get("riven_key"), riven_item_id, tvdb_id=tvdb_id_for_scrape)
        all_streams = await self.push_screen_wait(log_screen)
        
        if not all_streams:
            # We don't notify here because ScrapeLogScreen or the next block handles it
            pass
        else:
            # In case it returned None from a cancel
            if not isinstance(all_streams, dict):
                all_streams = {}

        streams = list(all_streams.values())
        if not streams:
            self.notify("No streams found.", severity="warning")
            return
        session_data = None
        while True:
            selection_screen = StreamSelectionScreen(streams)
            magnet_link = await self.app.push_screen_wait(selection_screen)
            if not magnet_link:
                return
            await self.start_spinner("Starting scrape session...")
            current_session_data, error = await self.api.start_scrape_session(media_type, magnet_link, tmdb_id, self.settings.get("riven_key"), riven_item_id, tvdb_id=tvdb_id_for_scrape)
            self.stop_spinner()
            if error and "Torrent is not cached" in error:
                self.notify("Torrent not cached. Please select another.", severity="warning")
                continue 
            elif error or not isinstance(current_session_data, dict):
                self.notify(f"Error starting session: {error or 'Invalid response'}", severity="error")
                return
            session_data = current_session_data
            break
        session_id = session_data.get("session_id")
        containers_files = session_data.get("containers", {}).get("files", [])
        if not session_id or not containers_files:
            self.notify("No cached files found in session.", severity="error")
            return

        if media_type == "movie":
            await self._finalize_movie_scrape(session_id, containers_files)
        elif media_type == "tv":
            await self._finalize_tv_scrape(session_id, containers_files)

    async def _finalize_movie_scrape(self, session_id: str, containers_files: List[dict]):
        main_content = self.query_one(MainContent)
        riven_key = self.settings.get("riven_key")
        
        # Select largest file for movie
        video_file = max(containers_files, key=lambda f: f.get('filesize', 0))
        file_id_str = str(video_file.get("file_id"))
        
        await self.api.parse_torrent_titles([video_file.get('filename')], riven_key)
        
        payload_for_select = {
            file_id_str: {
                "file_id": video_file.get("file_id"),
                "filename": video_file.get("filename"),
                "filesize": video_file.get("filesize"),
                "download_url": video_file.get("download_url")
            }
        }
        
        success, response = await self.api.select_scrape_file(session_id, payload_for_select, riven_key)
        if not success:
            self.notify(f"Error selecting file: {response}", severity="error")
            return

        await self.start_spinner("Updating scrape attributes...")
        await self.api.update_scrape_attributes(session_id, payload_for_select[file_id_str], riven_key)
        self.stop_spinner()
        
        await self.start_spinner("Completing scrape session...")
        final_success, final_response = await self.api.complete_scrape_session(session_id, riven_key)
        self.stop_spinner()
        
        if final_success:
            self.notify("Manual scrape initiated successfully!", severity="success")
            await self._refresh_current_item_data_and_ui(delay=self.refresh_delay_seconds) 
        else:
            self.notify(f"Finalization Error: {final_response}", severity="error")

    async def _finalize_tv_scrape(self, session_id: str, containers_files: List[dict]):
        main_content = self.query_one(MainContent)
        riven_key = self.settings.get("riven_key")
        
        filenames = [f.get("filename") for f in containers_files if f.get("filename")]
        response, error = await self.api.parse_torrent_titles(filenames, riven_key)
        if error:
            self.notify(f"Error parsing titles: {error}", severity="error")
            return
            
        parsed_files = response.get("data", [])
        title = main_content.tmdb_details.get('name', 'N/A')
        
        mapping_screen = FileMappingScreen(containers_files, parsed_files, title, session_id)
        file_mapping = await self.app.push_screen_wait(mapping_screen)
        
        if not file_mapping:
            return
            
        payload_for_select = {}
        for season in file_mapping:
            for episode in file_mapping[season]:
                file_data = file_mapping[season][episode]
                file_id_str = str(file_data.get("file_id"))
                payload_for_select[file_id_str] = file_data
                
        success, response = await self.api.select_scrape_file(session_id, payload_for_select, riven_key)
        if not success:
            self.notify(f"Error selecting files: {response}", severity="error")
            return

        await self.start_spinner("Updating scrape attributes...")
        await self.api.update_scrape_attributes(session_id, file_mapping, riven_key)
        self.stop_spinner()
        
        await self.start_spinner("Completing scrape session...")
        final_success, final_response = await self.api.complete_scrape_session(session_id, riven_key)
        self.stop_spinner()
        
        if final_success:
            self.notify("Manual scrape for TV show initiated successfully!", severity="success")
            await self._refresh_current_item_data_and_ui(delay=self.refresh_delay_seconds) 
        else:
            self.notify(f"Finalization Error: {final_response}", severity="error")

    @on(Button.Pressed, "#btn-add")
    async def handle_add(self):
        main_content = self.query_one(MainContent)
        if not main_content.tmdb_details:
            return
        tmdb_details = main_content.tmdb_details
        media_type = main_content.item_data.get("media_type")
        add_media_type = "tv" if media_type == "tv" else "movie"
        id_to_add = tmdb_details.get("external_ids", {}).get("tvdb_id") if media_type == "tv" else tmdb_details.get("id")
        id_type = "tvdb_ids" if media_type == "tv" else "tmdb_ids"
        title = tmdb_details.get("name") or tmdb_details.get("title")
        if not id_to_add:
            self.notify(f"Missing {id_type[:-1].upper()} for add.", severity="error")
            return
        self.notify(f"Adding '{title}' to library...")
        success, response = await self.api.add_item(add_media_type, id_type, str(id_to_add), self.settings.get("riven_key"))
        if success:
            self.notify(f"'{title}' added successfully!", severity="success")
            await self._refresh_current_item_data_and_ui(delay=self.refresh_delay_seconds) 
        else:
            self.notify(f"Failed to add '{title}': {response}", severity="error")

    @on(Button.Pressed, "#btn-clear-selection")
    async def on_clear_selection(self):
        if not self.library_selection:
            self.notify("No items selected.", severity="information")
            return
            
        count = len(self.library_selection)
        self.library_selection.clear()
        self.notify(f"Cleared selection ({count} items).", severity="success")
        
        # Refresh current library view to update checkboxes
        if self.last_library_filters:
            await self.show_library_items(**self.last_library_filters)
        else:
            await self.show_library_items()

    async def handle_bulk_action(self, action: str, display_name: str):
        if not self.library_selection:
            self.notify(f"No items selected for {display_name}.", severity="warning")
            return

        item_ids = list(self.library_selection.keys())
        count = len(item_ids)
        
        # Determine variant and message
        variant = "primary"
        if action == "remove": variant = "error"
        elif action == "reset": variant = "warning"
        
        message = f"Are you sure you want to [bold]{display_name}[/] [cyan]{count}[/] items?\n\n"
        message += "\n".join([f"• {title}" for title in list(self.library_selection.values())[:10]])
        if count > 10:
            message += f"\n... and {count - 10} more."

        confirmed = await self.push_screen_wait(ConfirmationScreen(
            f"Bulk {display_name}", 
            message, 
            confirm_label=f"Yes, {display_name}",
            variant=variant
        ))
        
        if not confirmed:
            return

        riven_key = self.settings.get("riven_key")
        self.log_message(f"Bulk {display_name}: Initiating for {count} items.")
        self.tui_logger.info(f"Bulk {display_name}: {count} items selected: {', '.join(self.library_selection.values())}")
        
        await self.start_spinner(f"{display_name}... ({count} items)")
        success, response = await self.api.bulk_action(action, item_ids, riven_key)
        self.stop_spinner()

        if success:
            self.notify(f"Successfully executed {display_name} on {count} items.", severity="success")
            self.log_message(f"Bulk {display_name}: Success.")
            self.library_selection.clear()
            if self.last_library_filters:
                await self.show_library_items(**self.last_library_filters)
        else:
            self.notify(f"Bulk {display_name} failed: {response}", severity="error")
            self.log_message(f"Bulk {display_name}: Failed. Error: {response}")

    @on(Button.Pressed, "#btn-adv-reset")
    def on_bulk_reset(self): self.run_worker(self.handle_bulk_action("reset", "Reset"))

    @on(Button.Pressed, "#btn-adv-retry")
    def on_bulk_retry(self): self.run_worker(self.handle_bulk_action("retry", "Retry"))

    @on(Button.Pressed, "#btn-adv-remove")
    def on_bulk_remove(self): self.run_worker(self.handle_bulk_action("remove", "Remove"))

    @on(Button.Pressed, "#btn-adv-pause")
    def on_bulk_pause(self): self.run_worker(self.handle_bulk_action("pause", "Pause"))

    @on(Button.Pressed, "#btn-adv-unpause")
    def on_bulk_unpause(self): self.run_worker(self.handle_bulk_action("unpause", "Unpause"))

    @on(Button.Pressed, "#btn-advanced-toggle")
    def on_advanced_toggle(self):
        self.query_one(Sidebar).toggle_advanced()

    @on(Button.Pressed, "#btn-apply-filters")
    async def on_apply_filters(self):
        sidebar = self.query_one(Sidebar)
        filters = sidebar.get_filter_values()
        
        await self.show_library_items(
            limit=filters["limit"],
            page=1, # Reset to page 1
            sort=filters["sort"],
            item_type=filters["type"],
            search=filters["search"],
            states=[filters["states"]] if filters["states"] else None,
        )

    @on(Button.Pressed)
    def on_calendar_day_click(self, event: Button.Pressed) -> None:
        if event.button.id and event.button.id.startswith("btn-cal-day-"):
            try:
                day = int(event.button.id.split("-")[-1])
                target_id = f"#day-group-{day}"
                main_content = self.query_one(MainContent)
                try:
                    target_widget = main_content.query_one(target_id)
                    target_widget.scroll_visible(top=True)
                except NoMatches:
                    pass
            except Exception:
                pass

if __name__ == "__main__":
    RivenTUI().run()
