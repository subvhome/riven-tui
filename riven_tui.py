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
from dashboard_view import DashboardView
from advanced_view import AdvancedView
from sidebar import Sidebar
from search import SearchArea, SearchSubmitted
from version import VERSION
import subprocess
import httpx

NOTIFICATION_CLEAR_DELAY = 10.0 # Seconds

class UpdateScreen(ModalScreen[bool]):
    def __init__(self, remote_version: str, name: str | None = None, id: str | None = None, classes: str | None = None) -> None:
        super().__init__(name=name, id=id, classes=f"{classes or ''} centered-modal-screen".strip())
        self.remote_version = remote_version

    def compose(self) -> ComposeResult:
        with Vertical(id="update-container", classes="modal-popup"):
            yield Static("✨ New Update Available", id="update-title")
            yield Static(f"Version [bold]{self.remote_version}[/bold] is now available.\n(Current: {VERSION})\n\nWould you like to update now?", id="update-message")
            
            with Vertical(id="update-progress-container", classes="hidden"):
                yield Label("Updating files...")
                yield ProgressBar(total=100, id="update-bar")
                yield Static("", id="update-details")

            with Horizontal(id="update-buttons"):
                yield Button("Update Now", id="btn-update-confirm", variant="success")
                yield Button("Later", id="btn-update-cancel")

    @on(Button.Pressed, "#btn-update-confirm")
    async def on_confirm(self) -> None:
        self.query_one("#update-buttons").display = False
        container = self.query_one("#update-progress-container")
        container.remove_class("hidden")
        self.run_worker(self.perform_git_pull())

    @on(Button.Pressed, "#btn-update-cancel")
    def on_cancel(self) -> None:
        self.dismiss(False)

    async def perform_git_pull(self):
        bar = self.query_one("#update-bar", ProgressBar)
        details = self.query_one("#update-details", Static)
        
        try:
            steps = [
                ("Fetching...", ["git", "fetch", "--all"]),
                ("Resetting...", ["git", "reset", "--hard", "origin/main"]),
                ("Pulling...", ["git", "pull", "origin", "main"]),
            ]
            
            for i, (msg, cmd) in enumerate(steps):
                details.update(f"[yellow]{msg}[/]")
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                
                if process.returncode != 0:
                    raise Exception(stderr.decode().strip())
                
                bar.advance(33.3)

            details.update("[bold green]Update successful![/]\n[cyan]The application will now exit.\nPlease relaunch to use the new version.")
            await asyncio.sleep(3)
            self.app.exit()
            
        except Exception as e:
            self.app.log_message(f"Update Error: {e}")
            details.update(f"[red]Update failed: {e}[/]")
            await asyncio.sleep(5)
            self.dismiss(False)

class MediaCardScreen(ModalScreen):
    def __init__(self, tmdb_data: dict, riven_data: dict, media_type: str, api: RivenAPI, settings: dict, chafa_available: bool):
        super().__init__(classes="centered-modal-screen")
        self.tmdb_data = tmdb_data
        self.riven_data = riven_data
        self.media_type = media_type
        self.api = api
        self.settings = settings
        self.chafa_available = chafa_available

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-media-card"):
            with Vertical(id="modal-scroll-area", classes="scrollable-container"):
                yield Vertical(id="modal-media-container")
                yield Vertical(id="modal-json-container", classes="hidden")
            yield Button("Back to Media", id="btn-back-from-json", variant="primary", classes="hidden")

    async def on_mount(self):
        container = self.query_one("#modal-media-container")
        tmdb_data = self.tmdb_data
        riven_data = self.riven_data
        
        title = tmdb_data.get('title') or tmdb_data.get('name', 'N/A')
        year = (tmdb_data.get('release_date') or tmdb_data.get('first_air_date', 'N/A'))[:4]
        tagline = tmdb_data.get('tagline')
        
        # Match show_item_actions logic for runtime
        runtime_movie = tmdb_data.get('runtime', 0)
        episode_run_time = None
        if self.media_type == "tv":
            episode_run_time_list = tmdb_data.get('episode_run_time', [])
            if episode_run_time_list:
                episode_run_time = f"{episode_run_time_list[0]} mins"

        genres = " - ".join([genre.get('name') for genre in tmdb_data.get('genres', []) if genre.get('name')])
        description = tmdb_data.get('overview')
        status = tmdb_data.get('status')
        
        languages_spoken_list = [lang.get('iso_639_1').upper() for lang in tmdb_data.get('spoken_languages', []) if lang.get('iso_639_1')]
        if not languages_spoken_list and tmdb_data.get('original_language'):
            languages_spoken_list.append(tmdb_data.get('original_language').upper())
        languages_spoken = " - ".join(languages_spoken_list)

        # 0. Status Label (Top)
        status_text = f"In Library (Riven ID: {riven_data.get('id')})" if riven_data else "Not in Library"
        await container.mount(Static(status_text, id="modal-status-label"))

        # 1. Header & Tagline
        await container.mount(Static(f"[bold]{title}[/bold]", classes="media-title"))
        if tagline:
            await container.mount(Static(f"[italic]{tagline}[/italic]", classes="media-tagline"))

        # 2. Action Buttons Row
        action_buttons = []
        if riven_data:
            action_buttons.extend([
                Button("Delete", id="btn-delete-modal", variant="error"),
                Button("Reset", id="btn-reset-modal", variant="warning"),
                Button("Retry", id="btn-retry-modal", variant="primary"),
            ])
        action_buttons.append(Button("Manual Scrape", id="btn-scrape-modal", variant="success"))
        if not riven_data:
            action_buttons.append(Button("Add to Library", id="btn-add-modal", variant="success"))
        
        action_buttons.append(Button("Back", id="btn-back-to-dashboard", variant="primary"))
        action_buttons.append(Button("JSON", id="btn-print-json-modal"))
        
        await container.mount(Horizontal(*action_buttons, classes="media-button-bar", id="modal-button-row"))

        # 3. Metadata Line
        meta_items = [year]
        if self.media_type == "movie" and runtime_movie:
            meta_items.append(f"{runtime_movie} mins")
        elif self.media_type == "tv" and episode_run_time:
            meta_items.append(episode_run_time)
            
        if languages_spoken:
            meta_items.append(languages_spoken)
        if status:
            meta_items.append(status)
            
        await container.mount(Static(" * ".join(filter(None, meta_items)), classes="media-metadata"))

        # 4. Genres & Description
        if genres:
            await container.mount(Static(f"Genres: {genres}", classes="media-genres"))
        if description:
            await container.mount(Static(description, classes="media-overview"))
            
        # Render poster
        if self.chafa_available and tmdb_data.get("poster_path"):
            poster_url = f"https://image.tmdb.org/t/p/w1280{tmdb_data['poster_path']}"
            poster_art, error = await self.api.get_poster_chafa(poster_url, width=50)
            if not error:
                await container.mount(Static(Text.from_ansi(poster_art), id="poster-display"))

    @on(Button.Pressed, "#btn-print-json-modal")
    async def handle_print_json(self):
        item = self.riven_data
        item_id = item.get("id") if item else None
        
        if item_id:
            await self.app.start_spinner("Fetching extended Riven data...")
            media_type = item.get("type", "movie")
            extended_data = await self.api.get_item_by_id(media_type, str(item_id), self.settings.get("riven_key"), extended=True)
            self.app.stop_spinner()
            data = extended_data or item
        else:
            data = {"info": "Item not in Riven library"}

        media_container = self.query_one("#modal-media-container")
        json_container = self.query_one("#modal-json-container")
        back_btn = self.query_one("#btn-back-from-json")

        await json_container.query("*").remove()
        formatted_json = json.dumps(data, indent=4)
        await json_container.mount(Static(formatted_json))

        media_container.add_class("hidden")
        json_container.remove_class("hidden")
        back_btn.remove_class("hidden")

    @on(Button.Pressed, "#btn-back-from-json")
    def handle_back_from_json(self):
        self.query_one("#modal-media-container").remove_class("hidden")
        self.query_one("#modal-json-container").add_class("hidden")
        self.query_one("#btn-back-from-json").add_class("hidden")

    @on(Button.Pressed, "#btn-back-to-dashboard")
    def exit_modal(self):
        self.dismiss()

    @on(Button.Pressed, "#btn-add-modal")
    async def handle_add(self):
        title = self.tmdb_data.get("name") or self.tmdb_data.get("title")
        id_to_add = self.tmdb_data.get("external_ids", {}).get("tvdb_id") if self.media_type == "tv" else self.tmdb_data.get("id")
        id_type = "tvdb_ids" if self.media_type == "tv" else "tmdb_ids"
        riven_type = "show" if self.media_type == "tv" else "movie"
        
        if not id_to_add:
            self.app.notify(f"Missing {id_type[:-1].upper()} for add.", severity="error")
            return

        self.app.notify(f"Adding '{title}' to library...")
        success, response = await self.api.add_item(riven_type, id_type, str(id_to_add), self.settings.get("riven_key"))
        if success:
            self.app.notify(f"'{title}' added successfully!", severity="success")
            self.dismiss()
            self.app.run_worker(self.app.refresh_dashboard())
        else:
            self.app.notify(f"Failed to add: {response}", severity="error")

    @on(Button.Pressed, "#btn-delete-modal")
    async def handle_delete(self):
        item_id = self.riven_data.get("id")
        success, _ = await self.api.delete_item(item_id, self.settings.get("riven_key"))
        if success:
            self.app.notify("Item deleted", severity="success")
            self.dismiss()
            self.app.run_worker(self.app.refresh_dashboard())
        else:
            self.app.notify("Failed to delete item.", severity="error")

    @on(Button.Pressed, "#btn-reset-modal")
    async def handle_reset(self):
        item_id = self.riven_data.get("id")
        success, _ = await self.api.reset_item(item_id, self.settings.get("riven_key"))
        if success:
            self.app.notify("Item reset successfully.", severity="information")
            self.dismiss()
        else:
            self.app.notify("Failed to reset item.", severity="error")

    @on(Button.Pressed, "#btn-retry-modal")
    async def handle_retry(self):
        item_id = self.riven_data.get("id")
        success, _ = await self.api.retry_item(item_id, self.settings.get("riven_key"))
        if success:
            self.app.notify("Item sent for retry.", severity="information")
            self.dismiss()
        else:
            self.app.notify("Failed to retry item.", severity="error")

    @on(Button.Pressed, "#btn-scrape-modal")
    def handle_scrape(self):
        self.dismiss()
        main_content = self.app.query_one(MainContent)
        main_content.item_data = {"id": self.tmdb_data.get("id"), "media_type": self.media_type}
        main_content.tmdb_details = self.tmdb_data
        main_content.item_details = self.riven_data
        self.app.run_worker(self.app._run_manual_scrape)

class ScrapeLogScreen(ModalScreen[dict]):
    def __init__(self, media_type: str, tmdb_id: int, riven_key: str, riven_item_id: str = None, tvdb_id: int = None, name: str | None = None, id: str | None = None, classes: str | None = None) -> None:
        super().__init__(name=name, id=id, classes=f"{classes or ''} centered-modal-screen".strip())
        self.media_type = media_type
        self.tmdb_id = tmdb_id
        self.riven_key = riven_key
        self.riven_item_id = riven_item_id
        self.tvdb_id = tvdb_id
        self.all_streams = {}

    def compose(self) -> ComposeResult:
        with Vertical(id="scrape-log-container", classes="modal-popup"):
            yield Static("Discovering streams...", id="scrape-log-title")
            yield Log(id="scrape-log", highlight=True)
            yield Button("Close", id="btn-close-scrape-log", variant="error")

    async def on_mount(self) -> None:
        self.run_worker(self.run_discovery())

    async def run_discovery(self):
        log_widget = self.query_one(Log)
        log_widget.write_line("Starting stream discovery...")
        try:
            async for line in self.app.api.scrape_stream(
                self.media_type, self.tmdb_id, self.riven_key, self.riven_item_id, tvdb_id=self.tvdb_id
            ):
                if line.startswith("data:"):
                    data_content = line[len("data:"):].strip()
                    if data_content == "[DONE]":
                        break
                    try:
                        message_data = json.loads(data_content)
                        if 'message' in message_data:
                            log_widget.write_line(f"-> {message_data['message']}")
                        if 'streams' in message_data and message_data['streams']:
                            self.all_streams.update(message_data['streams'])
                    except json.JSONDecodeError:
                        continue
                elif line.startswith("error:"):
                    log_widget.write_line(f"ERROR: {line}")
            
            log_widget.write_line("Discovery complete.")
            await asyncio.sleep(1)
            self.dismiss(self.all_streams)
        except Exception as e:
            log_widget.write_line(f"Unexpected error: {e}")

    @on(Button.Pressed, "#btn-close-scrape-log")
    def on_close_button(self, event: Button.Pressed):
        self.dismiss(self.all_streams)

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
            success, response = await self.app.api.abort_scrape_session(self.session_id, self.app.settings.get("riven_key"))
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


class RefreshPoster(Message):
    pass

class CalendarItemSelected(Message):
    def __init__(self, item_data: dict) -> None:
        super().__init__()
        self.item_data = item_data

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

    def on_click(self) -> None:
        self.post_message(CalendarItemSelected(self.item_data))

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
        with Vertical(id="main-content-scroll-area"):
            yield Vertical(id="main-content-container")
            yield Vertical(id="main-content-json-container", classes="hidden")
        yield Button("Back", id="btn-back-to-actions", variant="primary", classes="hidden")

    async def display_logs(self, logs: str):
        container = self.query_one("#main-content-container")
        await container.query("*").remove()
        await container.mount(Static(logs, id="log-content", expand=True))
        await container.mount(Button("Refresh", id="btn-refresh-logs", variant="primary"))

    async def display_json(self, data: dict):
        container = self.query_one("#main-content-container")
        json_container = self.query_one("#main-content-json-container")
        back_btn = self.query_one("#btn-back-to-actions")

        await json_container.query("*").remove()
        formatted_json = json.dumps(data, indent=4)
        await json_container.mount(Static(formatted_json))

        container.add_class("hidden")
        json_container.remove_class("hidden")
        back_btn.remove_class("hidden")

    @on(Button.Pressed, "#btn-back-to-actions")
    async def handle_back_to_actions(self):
        self.query_one("#main-content-container").remove_class("hidden")
        self.query_one("#main-content-json-container").add_class("hidden")
        self.query_one("#btn-back-to-actions").add_class("hidden")

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
        self.calendar_cache: List[dict] = [] 
        self.navigation_source: Literal["dashboard", "library", "search", "calendar"] = "dashboard"
        self.current_trending_page = 1

    def log_message(self, message: str):
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
            self.file_logger.error(f"Error loading settings.json: {e}")
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
        
    def action_toggle_debug(self) -> None:
        try:
            log_widget = self.query_one("#debug-log", Log)
            log_widget.toggle_class("hidden")
        except NoMatches:
            pass

    def compose(self) -> ComposeResult:
        with Horizontal(id="header-bar"):
            yield Button("Dashboard", id="btn-header-dashboard")
            yield Button("Search", id="btn-header-search")
            yield Button("Library", id="btn-header-library")
            yield Button("Discover", id="btn-header-discover")
            yield Button("Advanced", id="btn-header-advanced")
            yield Button("Calendar", id="btn-header-calendar")
            yield Button("Settings", id="btn-header-settings")
            yield Button("Logs", id="btn-header-logs")
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
            
            yield SettingsView(id="settings-view")
            yield AdvancedView(id="advanced-view")
            yield LogsView(id="logs-view")

        yield Log(id="debug-log", highlight=True, classes="hidden")

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
        self.log_message("App mounted. Starting startup worker.")
        self.run_worker(self.perform_startup())

    async def perform_startup(self) -> None:
        import os
        import shutil
        if os.path.exists("y") and os.path.isdir("y"):
            try:
                shutil.rmtree("y")
                self.log_message("Auto-Cleanup: Removed redundant 'y/' folder.")
            except Exception as e:
                self.log_message(f"Auto-Cleanup Error (y/): {e}")

        if "api_key" in self.settings and "riven_key" not in self.settings:
            self.settings["riven_key"] = self.settings.pop("api_key")
            self.log_message("Migrating api_key to riven_key in settings.json...")
            try:
                with open("settings.json", "w") as f:
                    json.dump(self.settings, f, indent=4)
            except Exception as e:
                self.log_message(f"Migration Error (Saving): {e}")

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
            self.run_worker(self.check_for_updates())
        except Exception as e:
            self.log_message(f"Config Error: {e}")
            self.notify(f"Config Error: {e}", severity="error")

    async def on_unmount(self) -> None:
        if hasattr(self, "api"):
            await self.api.shutdown()

    async def refresh_dashboard(self):
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
            self.log_message(f"Dashboard: API tasks completed. Results count: {len(results)}")
        except Exception as e:
            self.log_message(f"Dashboard: Error in asyncio.gather: {e}")
            return
        
        stats_resp = results[0] if not isinstance(results[0], Exception) else (None, str(results[0]))
        health_resp = results[1] if not isinstance(results[1], Exception) else (None, str(results[1]))
        recent_resp = results[2] if not isinstance(results[2], Exception) else (None, str(results[2]))
        trending_resp = results[3] if not isinstance(results[3], Exception) else (None, str(results[3]))
        services_resp = results[4] if not isinstance(results[4], Exception) else (None, str(results[4]))
        settings_resp = results[5] if not isinstance(results[5], Exception) else (None, str(results[5]))
        
        stats_data = stats_resp[0] if stats_resp and stats_resp[0] else {}
        
        # Parse health response
        health_ok = False
        if health_resp and health_resp[0]:
            health_ok = health_resp[0].get("message") == "True"
        
        self.log_message("Dashboard: Updating UI components...")
        await dashboard_view.update_stats(stats_data, health_ok)
        
        # Update recently added
        if recent_resp and recent_resp[0]:
            await dashboard_view.update_recently_added(recent_resp[0].get("items", []))
            
        # Update trending
        if trending_resp and trending_resp[0]:
            # Show the list immediately (as unknown status)
            await dashboard_view.update_trending(trending_resp[0])
            # Trigger background check for library status
            self.run_worker(self._check_trending_library_status(trending_resp[0]))

        # Update service pills
        if services_resp and services_resp[0] and settings_resp and settings_resp[0]:
            await dashboard_view.update_service_pills(services_resp[0], settings_resp[0])

        # Update distribution grid
        if stats_data.get("states"):
            await dashboard_view.update_states_overview(stats_data["states"])
        
        self.log_message("Dashboard: Refresh complete.")

    def watch_app_state(self, new_state: Literal["welcome", "dashboard", "search", "library", "calendar", "settings", "advanced"]) -> None:
        welcome_message = self.query_one("#welcome-message")
        search_subheader = self.query_one("#search-subheader")
        main_area = self.query_one("#main-area")
        sidebar = self.query_one(Sidebar)
        main_content = self.query_one(MainContent)
        search_input = self.query_one("#search-input")
        settings_view = self.query_one(SettingsView)
        dashboard_view = self.query_one(DashboardView)
        dashboard_wrapper = self.query_one("#dashboard-wrapper")
        advanced_view = self.query_one(AdvancedView)
        logs_view = self.query_one("#logs-view")

        welcome_message.display = False
        search_subheader.display = False
        main_area.display = False
        sidebar.display = False
        main_content.display = False
        settings_view.display = False
        dashboard_view.display = False
        dashboard_wrapper.display = False
        advanced_view.display = False
        logs_view.display = False

        # Update Tab Classes
        for btn in self.query("#header-bar Button"):
            btn.remove_class("-active")
        
        try:
            target_btn = self.query_one(f"#btn-header-{new_state}")
            target_btn.add_class("-active")
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
            search_subheader.display = True
            main_area.display = True
            sidebar.display = True 
            sidebar.show_blank()
            main_content.display = True 
            search_input.focus()
            main_content.query_one("#main-content-container").remove_children()
            main_content.query_one("#main-content-title").display = False
        elif new_state == "library":
            search_subheader.display = False 
            main_area.display = True
            sidebar.display = True 
            sidebar.show_library_filters() 
            main_content.display = True
        elif new_state == "calendar":
            search_subheader.display = False
            main_area.display = True
            sidebar.display = True 
            sidebar.show_calendar_summary() 
            main_content.display = True
            main_content.query_one("#main-content-title").display = False
            main_content.query_one("#main-content-container").remove_children()
        elif new_state == "settings":
            settings_view.display = True
            sidebar.display = True
            sidebar.show_blank()
            main_area.display = True
            if not settings_view.settings_data:
                settings_view.post_message(Button.Pressed(settings_view.query_one("#btn-refresh-settings")))
        elif new_state == "logs":
            logs_view.display = True
            # Full width, no sidebar
            main_area.display = False
            sidebar.display = False
    @on(Button.Pressed, "#btn-header-dashboard")
    async def on_dashboard_button_pressed(self) -> None: 
        self.app_state = "dashboard"
        self.watch_app_state("dashboard")

    @on(Button.Pressed, "#btn-header-search")
    async def on_search_button_pressed(self) -> None: 
        self.app_state = "search"
        self.watch_app_state("search")

    @on(Button.Pressed, "#btn-header-library")
    async def on_library_button_pressed(self) -> None: 
        self.app_state = "library" 
        self.watch_app_state("library")
        await self.show_library_items(refresh_cache=True)

    @on(Button.Pressed, "#btn-header-advanced")
    async def on_advanced_button_pressed(self) -> None:
        self.app_state = "advanced"
        self.watch_app_state("advanced")

    @on(Button.Pressed, "#btn-header-calendar")
    async def on_calendar_button_pressed(self) -> None:
        self.app_state = "calendar"
        self.watch_app_state("calendar")
        await self.show_calendar(refresh_cache=True)

    @on(Button.Pressed, "#btn-header-settings")
    async def on_settings_button_pressed(self) -> None:
        self.app_state = "settings"
        self.watch_app_state("settings")

    @on(Button.Pressed, "#btn-header-logs")
    async def on_logs_button_pressed(self) -> None:
        self.app_state = "logs"
        self.watch_app_state("logs")
        await self.query_one("#logs-view").update_logs(refresh_all=True)

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
            await self.show_item_actions()

    @on(SearchSubmitted)
    async def handle_search(self, message: SearchSubmitted):
        self.app_state = "search" 
        sidebar = self.query_one(Sidebar)
        sidebar.query_one(ListView).clear() 

        main_content = self.query_one(MainContent)
        container = main_content.query_one("#main-content-container")
        
        # Reset visibility
        container.remove_class("hidden")
        main_content.query_one("#main-content-json-container").add_class("hidden")
        main_content.query_one("#btn-back-to-actions").add_class("hidden")

        await container.query("*").remove() 
        main_content.query_one("#main-content-title").display = False

        await self.start_spinner(f"Searching for '{message.query}'")
        results, error = await self.api.search_tmdb(message.query, self.settings.get("tmdb_bearer_token"))
        self.stop_spinner()
        if error:
            self.notify(f"TMDB Error: {error}", severity="error")
            return
        results.sort(key=lambda x: x.get('popularity', 0) or 0, reverse=True)
        sidebar.update_results(message.query, results)

    async def _render_poster(self, container: Container, tmdb_data: dict):
        if self.chafa_available and tmdb_data.get("poster_path"):
            main_content = self.query_one(MainContent)
            poster_url = f"https://image.tmdb.org/t/p/w1280{tmdb_data['poster_path']}"
            main_content_width = main_content.size.width
            chafa_target_width = max(10, main_content_width - 6)
            chafa_max_width = self.settings.get("chafa_max_width", 50)
            if chafa_max_width > 0:
                chafa_target_width = min(chafa_target_width, chafa_max_width)
            poster_art, error = await self.api.get_poster_chafa(poster_url, width=chafa_target_width)
            if not error:
                await container.mount(Static(Text.from_ansi(poster_art), id="poster-display"))
                main_content.last_chafa_width = chafa_target_width

    async def show_item_actions(self):
        main_content = self.query_one(MainContent)
        title_widget = main_content.query_one("#main-content-title")
        container = main_content.query_one("#main-content-container")

        # Reset visibility
        container.remove_class("hidden")
        main_content.query_one("#main-content-json-container").add_class("hidden")
        main_content.query_one("#btn-back-to-actions").add_class("hidden")

        await container.query("*").remove()
        main_content.last_chafa_width = None 
        tmdb_data = main_content.tmdb_details
        riven_data = main_content.item_details
        search_item_data = main_content.item_data 
        if not tmdb_data:
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
        action_buttons.append(Button("Back", id="btn-back-to-library", variant="primary"))
        action_buttons.append(Button("JSON", id="btn-print-json"))
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

    @on(DashboardView.DashboardItem.Clicked)
    async def on_dashboard_item_clicked(self, message: DashboardView.DashboardItem.Clicked) -> None:
        self.navigation_source = "dashboard"
        item = message.item_data
        source = message.source
        
        tmdb_id = None
        media_type = None
        
        if source == "library":
            tmdb_id = item.get("tmdb_id")
            if not tmdb_id and "parent_ids" in item:
                tmdb_id = item["parent_ids"].get("tmdb_id")
            
            media_type = item.get("type", "movie")
            if media_type == "show":
                media_type = "tv"
            
            # Resolve if still missing
            if not tmdb_id:
                external_id = item.get("tvdb_id") or (item.get("parent_ids") or {}).get("tvdb_id")
                source_type = "tvdb_id"
                if not external_id:
                    external_id = item.get("imdb_id") or (item.get("parent_ids") or {}).get("imdb_id")
                    source_type = "imdb_id"
                
                if external_id:
                    await self.start_spinner(f"Resolving details for '{item.get('title')}'...")
                    resolved_id, err = await self.api.find_tmdb_id(str(external_id), source_type, self.settings.get("tmdb_bearer_token"))
                    self.stop_spinner()
                    if resolved_id:
                        tmdb_id = resolved_id
        else: # trending
            tmdb_id = item.get("id")
            media_type = item.get("media_type", "movie")

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
        riven_id_to_check = tmdb_details.get("external_ids", {}).get("tvdb_id") if media_type == "tv" else tmdb_id
        
        riven_details = None
        if riven_id_to_check:
            riven_details = await self.api.get_item_by_id(riven_media_type, str(riven_id_to_check), self.settings.get("riven_key"))
            
        self.stop_spinner()
        
        # Set state for manual scrape integration
        main_content = self.query_one(MainContent)
        main_content.tmdb_details = tmdb_details
        main_content.item_details = riven_details
        main_content.item_data = {"id": tmdb_id, "media_type": media_type}

        self.push_screen(MediaCardScreen(tmdb_details, riven_details, media_type, self.api, self.settings, self.chafa_available))

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

        # Map 'tv' to 'show' for Riven add endpoint
        riven_media_type = "movie" if media_type == "movie" else "show"
        
        success, response = await self.api.add_item(riven_media_type, id_type, target_id, riven_key)
        if success:
            self.notify(f"'{title}' added successfully!", severity="success")
            # Refresh the dashboard to update the [+] button status
            self.run_worker(self.refresh_dashboard())
        else:
            self.notify(f"Failed to add '{title}': {response}", severity="error")

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
        riven_media_type = "tv" if media_type == "tv" else "movie"
        riven_id_to_check = tmdb_details.get("external_ids", {}).get("tvdb_id") if media_type == "tv" else tmdb_id
        if not riven_id_to_check:
            main_content.item_details = None
        else:
            main_content.item_details = await self.api.get_item_by_id(riven_media_type, str(riven_id_to_check), self.settings.get("riven_key"))
        self.stop_spinner() 
        await self.show_item_actions() 

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
        
        await container.query("*").remove() 
        await self.start_spinner("Fetching library...")
        
        riven_key = self.settings.get("riven_key")
        
        # Determine the types to send to the API. 
        # If item_type is None (All), we explicitly ask for movies and shows to exclude episodes/seasons.
        api_item_type = item_type
        if api_item_type is None:
            api_item_type = ["movie", "show"]
            
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
            count_only=count_only
        )
        
        self.stop_spinner()

        if err:
            self.notify(f"API Error: {err}", severity="error")
            return

        items = resp.get("items", [])
        total_count = resp.get("total_items", resp.get("total", 0))
        total_pages = resp.get("total_pages", math.ceil(total_count / limit) if limit > 0 else 1)

        if not items:
            await container.mount(Static("No library items found matching your filters.", id="empty-library-msg"))
        else:
            for item in items:
                title = item.get("title") or "Unknown"
                media_type = item.get("type", "movie")
                state = item.get("state", "Unknown")
                content_rating = item.get("content_rating") or "N/A"
                
                item_display_widget = LibraryItemCard(
                    item,
                    f"[bold]{title}[/bold]\n"
                    f"State: {state} | Content Rating: {content_rating}",
                    classes="library-item-card"
                )
                item_display_widget.add_class(f"library-item-{media_type}")
                await container.mount(item_display_widget)
                
        sidebar = self.query_one(Sidebar)
        pagination_area = sidebar.query_one("#sidebar-lib-pagination")
        await pagination_area.query("*").remove()
        await pagination_area.mount(PaginationControl(page, total_pages))

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
                self.notify(f"Resolving TMDB ID for '{item_data.get('title')}'...", severity="information")
                resolved_id, err = await self.api.find_tmdb_id(str(external_id), source, self.settings.get("tmdb_bearer_token"))
                if resolved_id:
                    tmdb_id = resolved_id
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
            # Manually trigger the watch logic to restore visibility
            self.watch_app_state("dashboard")
        elif self.navigation_source == "library":
            if self.last_library_filters:
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
                new_page = current_page - 1
                try:
                    self.query_one("#lib-filter-page", Input).value = str(new_page)
                except: pass
                self.post_message(PageChanged(new_page))

    @on(Button.Pressed, "#btn-next-page")
    async def on_next_page_click(self, event: Button.Pressed):
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

    @on(PageChanged)
    async def on_page_changed(self, event: PageChanged):
        if not self.last_library_filters:
            self.last_library_filters = {"page": 1, "limit": 20}
        
        self.last_library_filters["page"] = event.page
        await self.show_library_items(**self.last_library_filters)
        try:
            page_input = self.query_one("#lib-filter-page", Input)
            page_input.value = str(event.page)
        except: pass
        await self.show_library_items(**self.last_library_filters)

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
        item = main_content.item_details
        
        if item and item.get("id"):
            item_id = item.get("id")
            media_type = item.get("type", "movie")
            
            await self.start_spinner("Fetching extended Riven data...")
            extended_data = await self.api.get_item_by_id(media_type, str(item_id), self.settings.get("riven_key"), extended=True)
            self.stop_spinner()
            
            data = extended_data or item
        else:
            data = {"info": "Item not in Riven library"}
            
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
            video_file = max(containers_files, key=lambda f: f.get('filesize', 0))
            file_id_str = str(video_file.get("file_id"))
            await self.api.parse_torrent_titles([video_file.get('filename')], self.settings.get("riven_key"))
            payload_for_select = {
                file_id_str: {
                    "file_id": video_file.get("file_id"),
                    "filename": video_file.get("filename"),
                    "filesize": video_file.get("filesize"),
                    "download_url": video_file.get("download_url")
                }
            }
            success, response = await self.api.select_scrape_file(session_id, payload_for_select, self.settings.get("riven_key") )
            if success:
                await self.start_spinner("Updating scrape attributes...")
                update_payload = payload_for_select[file_id_str]
                await self.api.update_scrape_attributes(session_id, update_payload, self.settings.get("riven_key") )
                self.stop_spinner()
                await self.start_spinner("Completing scrape session...")
                final_success, final_response = await self.api.complete_scrape_session(session_id, self.settings.get("riven_key") )
                self.stop_spinner()
                if final_success:
                    self.notify("Manual scrape initiated successfully!", severity="success")
                    await self._refresh_current_item_data_and_ui(delay=self.refresh_delay_seconds) 
                else:
                    self.notify(f"Finalization Error: {final_response}", severity="error")
            else:
                self.notify(f"Error selecting file: {response}", severity="error")
        elif media_type == "tv":
            filenames = [f.get("filename") for f in containers_files if f.get("filename")]
            response, error = await self.api.parse_torrent_titles(filenames, self.settings.get("riven_key"))
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
            success, response = await self.api.select_scrape_file(session_id, payload_for_select, self.settings.get("riven_key") )
            if success:
                await self.start_spinner("Updating scrape attributes...")
                await self.api.update_scrape_attributes(session_id, file_mapping, self.settings.get("riven_key") )
                self.stop_spinner()
                await self.start_spinner("Completing scrape session...")
                final_success, final_response = await self.api.complete_scrape_session(session_id, self.settings.get("riven_key") )
                self.stop_spinner()
                if final_success:
                    self.notify("Manual scrape for TV show initiated successfully!", severity="success")
                    await self._refresh_current_item_data_and_ui(delay=self.refresh_delay_seconds) 
                else:
                    self.notify(f"Finalization Error: {final_response}", severity="error")
            else:
                self.notify(f"Error selecting files: {response}", severity="error")

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
