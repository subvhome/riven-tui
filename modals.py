import json
import asyncio
from typing import List, Optional
from textual import on
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.containers import Vertical, Horizontal
from textual.widgets import Static, Label, Button, ProgressBar, Log, ListView, ListItem, Input
from textual.css.query import NoMatches
from rich.text import Text
from rich.markup import escape

from version import VERSION
from api import RivenAPI
from messages import RefreshPoster

class ConfirmationScreen(ModalScreen[bool]):
    def __init__(self, title: str, message: str, confirm_label: str = "Confirm", cancel_label: str = "Cancel", variant: str = "primary"):
        super().__init__(classes="centered-modal-screen")
        self.title_text = title
        self.message_text = message
        self.confirm_label = confirm_label
        self.cancel_label = cancel_label
        self.variant = variant

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-popup", id="confirmation-container"):
            yield Static(f"⚠️ {self.title_text}", id="confirmation-title")
            yield Static(self.message_text, id="confirmation-message")
            with Horizontal(classes="modal-button-row"):
                yield Button(self.confirm_label, id="btn-confirm", variant=self.variant)
                yield Button(self.cancel_label, id="btn-cancel")

    @on(Button.Pressed, "#btn-confirm")
    def on_confirm(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#btn-cancel")
    def on_cancel(self) -> None:
        self.dismiss(False)

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
        import sys
        
        try:
            steps = [
                ("Fetching...", ["git", "fetch", "--all"]),
                ("Resetting...", ["git", "reset", "--hard", "origin/main"]),
                ("Pulling...", ["git", "pull", "origin", "main"]),
                ("Updating dependencies...", [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"]),
            ]
            
            step_increment = 100 / len(steps)
            
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
                
                bar.advance(step_increment)

            details.update("[bold green]Update successful![/]\n[cyan]The application will now exit.\nPlease relaunch to use the new version.")
            await asyncio.sleep(3)
            self.app.exit()
            
        except Exception as e:
            if hasattr(self.app, "log_message"):
                self.app.log_message(f"Update Error: {e}")
            details.update(f"[red]Update failed: {e}[/]")
            await asyncio.sleep(5)
            self.dismiss(False)

class MediaCardScreen(ModalScreen):
    last_chafa_width: Optional[int] = None

    def __init__(self, tmdb_data: dict, riven_data: dict, media_type: str, api: RivenAPI, settings: dict, chafa_available: bool):
        super().__init__(classes="centered-modal-screen")
        self.tmdb_data = tmdb_data
        self.riven_data = riven_data
        self.media_type = media_type
        self.api = api
        self.settings = settings
        self.chafa_available = chafa_available
        self.post_message_debounce_timer = None

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-media-card"):
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

        meta_items = [year]
        if self.media_type == "movie" and runtime_movie:
            meta_items.append(f"{runtime_movie} mins")
        elif self.media_type == "tv" and episode_run_time:
            meta_items.append(episode_run_time)
            
        if languages_spoken:
            meta_items.append(languages_spoken)
        if status:
            meta_items.append(status)
        if riven_data:
            meta_items.append(f"[bold]{riven_data.get('state', 'Unknown').title()}[/]")
            
        await info_col.mount(Static(" • ".join(filter(None, meta_items)), classes="media-metadata"))

        if genres:
            await info_col.mount(Static(genres, classes="media-genres"))
        if description:
            await info_col.mount(Static(description, classes="media-overview"))

        # 2. Populate Action Column (Right)
        action_buttons = []
        if riven_data:
            action_buttons.extend([
                Button("Delete", id="btn-delete-modal", variant="error"),
                Button("Reset", id="btn-reset-modal", variant="warning"),
                Button("Retry", id="btn-retry-modal", variant="primary"),
            ])
        action_buttons.append(Button("Manual Scrape", id="btn-scrape-modal", variant="success", disabled=True))
        if not riven_data:
            action_buttons.append(Button("Request", id="btn-add-modal", variant="success"))
        
        action_buttons.append(Button("Back", id="btn-back-to-dashboard", variant="primary"))
        action_buttons.append(Button("JSON", id="btn-print-json-modal"))
        
        # Use a Horizontal bar with an ID that is docked in CSS
        await action_col.mount(Horizontal(*action_buttons, id="modal-button-row", classes="media-button-bar"))

        if self.chafa_available and tmdb_data.get("poster_path"):
            await action_col.mount(Static(id="poster-display-modal"))
            self.last_chafa_width = None
            self.set_timer(0.1, lambda: self.post_message(RefreshPoster()))

    async def on_resize(self, event) -> None:
        if self.chafa_available and self.tmdb_data.get("poster_path"):
            if self.post_message_debounce_timer:
                self.post_message_debounce_timer.stop()
            self.post_message_debounce_timer = self.set_timer(0.2, lambda: self.post_message(RefreshPoster()))

    @on(RefreshPoster)
    async def on_refresh_poster(self, message: RefreshPoster) -> None:
        try:
            poster_widget = self.query_one("#poster-display-modal", Static)
        except NoMatches:
            return

        # Try to measure the actual action column if it exists (most accurate)
        target_width = None
        try:
            action_col = self.query_one(".media-action-column")
            if action_col.size.width > 0:
                # Subtract padding (2) + border (1) + safety (3) = 6
                target_width = max(10, action_col.size.width - 6)
        except NoMatches:
            pass

        if target_width is None:
            # Fallback calculation
            container = self.query_one("#modal-media-container")
            target_width = max(10, int(container.size.width * 0.75) - 14)

        chafa_max_width = self.settings.get("chafa_max_width", 50)
        if chafa_max_width > 0:
            target_width = min(target_width, chafa_max_width)

        target_height = int(target_width * 0.75)

        if self.last_chafa_width is None or abs(target_width - self.last_chafa_width) > 2:
            poster_url = f"https://image.tmdb.org/t/p/w1280{self.tmdb_data['poster_path']}"
            poster_art, error = await self.api.get_poster_chafa(poster_url, width=target_width, height=target_height)
            if not error:
                poster_widget.update(Text.from_ansi(poster_art))
                self.last_chafa_width = target_width

    @on(Button.Pressed, "#btn-print-json-modal")
    async def handle_print_json(self):
        tmdb_id = self.tmdb_data.get("id")
        tvdb_id = self.tmdb_data.get("external_ids", {}).get("tvdb_id")
        
        media_type = "tv" if self.media_type == "tv" else "movie"
        external_id = str(tvdb_id) if media_type == "tv" and tvdb_id else str(tmdb_id)

        if hasattr(self.app, "start_spinner"):
            await self.app.start_spinner("Fetching extended Riven data...")
        extended_data = await self.api.get_item_by_id(media_type, external_id, self.settings.get("riven_key"), extended=True)
        if hasattr(self.app, "stop_spinner"):
            self.app.stop_spinner()
        
        data = extended_data or self.riven_data or {"info": "Item not in Riven library"}

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
        riven_type = "tv" if self.media_type == "tv" else "movie"
        
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
    def on_delete_click(self) -> None:
        self.app.run_worker(self.handle_delete())

    async def handle_delete(self):
        item_id = self.riven_data.get("id")
        title = self.tmdb_data.get("title") or self.tmdb_data.get("name") or "Unknown Item"
        
        confirmed = await self.app.push_screen_wait(ConfirmationScreen(
            "Delete Item",
            f"Are you sure you want to delete [bold]{title}[/] from your library?",
            confirm_label="Yes, Delete",
            variant="error"
        ))
        
        if not confirmed:
            return

        success, _ = await self.api.delete_item(item_id, self.settings.get("riven_key"))
        if success:
            self.app.notify("Item deleted", severity="success")
            self.dismiss()
            self.app.run_worker(self.app.refresh_dashboard())
        else:
            self.app.notify("Failed to delete item.", severity="error")

    @on(Button.Pressed, "#btn-reset-modal")
    def on_reset_click(self) -> None:
        self.app.run_worker(self.handle_reset())

    async def handle_reset(self):
        item_id = self.riven_data.get("id")
        title = self.tmdb_data.get("title") or self.tmdb_data.get("name") or "Unknown Item"

        confirmed = await self.app.push_screen_wait(ConfirmationScreen(
            "Reset Item",
            f"Are you sure you want to reset [bold]{title}[/]?\nThis will restart the download/scrape process.",
            confirm_label="Yes, Reset",
            variant="warning"
        ))
        
        if not confirmed:
            return

        success, _ = await self.api.reset_item(item_id, self.settings.get("riven_key"))
        if success:
            self.app.notify("Item reset successfully.", severity="information")
            self.dismiss()
        else:
            self.app.notify("Failed to reset item.", severity="error")

    @on(Button.Pressed, "#btn-retry-modal")
    def on_retry_click(self) -> None:
        self.app.run_worker(self.handle_retry())

    async def handle_retry(self):
        item_id = self.riven_data.get("id")
        title = self.tmdb_data.get("title") or self.tmdb_data.get("name") or "Unknown Item"

        confirmed = await self.app.push_screen_wait(ConfirmationScreen(
            "Retry Item",
            f"Are you sure you want to retry [bold]{title}[/]?\nThis will attempt to re-process the item.",
            confirm_label="Yes, Retry",
            variant="primary"
        ))
        
        if not confirmed:
            return

        success, _ = await self.api.retry_item(item_id, self.settings.get("riven_key"))
        if success:
            self.app.notify("Item sent for retry.", severity="information")
            self.dismiss()
        else:
            self.app.notify("Failed to retry item.", severity="error")

    @on(Button.Pressed, "#btn-scrape-modal")
    def handle_scrape(self):
        result = {
            "action": "trigger_manual_scrape",
            "item_data": {"id": self.tmdb_data.get("id"), "media_type": self.media_type},
            "tmdb_details": self.tmdb_data,
            "item_details": self.riven_data
        }
        self.dismiss(result)

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
                    data_content = line[len("data:"):
].strip()
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
                self.app.notify("Invalid season or episode number. Please enter valid integers.", severity="error")
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
                self.app.notify("No files were mapped. Please map at least one file.", severity="warning")
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
