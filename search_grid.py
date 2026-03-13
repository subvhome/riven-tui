from textual.app import ComposeResult
from textual.widgets import Static, Label
from textual.containers import Vertical, Horizontal
from textual.message import Message
from textual import events
from rich.text import Text

HOVER_DELAY = 2.0 

class SearchGridTile(Vertical):
    can_focus = True
    BINDINGS = [("enter", "select", "Select")]

    class Selected(Message):
        def __init__(self, item_data: dict) -> None:
            self.item_data = item_data
            super().__init__()

    def __init__(self, item_data: dict, api) -> None:
        super().__init__(classes="search-tile")
        self.item_data = item_data
        self.api = api
        self._hover_timer = None
        self._is_active = False
        self._loading_poster = False
        self.can_focus_children = False
        # NEW: We need a variable to track the active background download
        self._render_worker = None

    def compose(self) -> ComposeResult:
        title = self.item_data.get('title') or self.item_data.get('name') or "Unknown"
        date = self.item_data.get('release_date') or self.item_data.get('first_air_date')
        year = date[:4] if date else "????"
        rating = self.item_data.get('vote_average') or 0
        rating_str = f"⭐ {rating:.1f}" if rating > 0 else ""
        state = self.item_data.get('state')
        state_str = state.title() if state else ""
        media_type = self.item_data.get('media_type', 'unknown').upper()

        # REMOVED .hidden class so layers can control visibility via offset
        yield Static(id="tile-poster")

        with Vertical(id="tile-info"):
            with Horizontal(classes="tile-header"):
                yield Label(state_str, classes=f"tile-state state-{state.lower() if state else 'none'}")
                yield Label(rating_str, classes="tile-rating")
            with Vertical(classes="tile-body"):
                yield Label(title, classes="tile-title")
            with Horizontal(classes="tile-footer"):
                yield Label(f"{'🎬' if media_type == 'MOVIE' else '📺'} {media_type}", classes="tile-type")
                yield Label(year, classes="tile-year")
                
    def action_select(self) -> None: self.post_message(self.Selected(self.item_data))
    def on_click(self) -> None: self.post_message(self.Selected(self.item_data))
    def on_enter(self, event: events.Enter) -> None:
        self._is_active = True
        self.add_class("-mouse-over")
        if self._hover_timer:
            self._hover_timer.stop()
        self._hover_timer = self.set_timer(HOVER_DELAY, self._load_poster)

    def on_leave(self, event: events.Leave) -> None:
        if self.app.mouse_position:
            mx, my = self.app.mouse_position
            if self.region.contains(mx, my):
                return
        
        self._is_active = False
        self._loading_poster = False
        self.remove_class("-mouse-over")
        self.remove_class("-show-poster")
        
        # THE FIX: Textual workers use .is_running
        if self._render_worker and self._render_worker.is_running:
            self._render_worker.cancel()
            self._render_worker = None
            
        self._reset_view()
        
    def on_focus(self, event: events.Focus) -> None:
        self._is_active = True
        self.add_class("-hover-loading")
        self._hover_timer = self.set_timer(HOVER_DELAY, self._load_poster)
    def on_blur(self, event: events.Blur) -> None:
        self._is_active = False
        self.remove_class("-mouse-over")
        self.remove_class("-show-poster")
        self._reset_view()
        
    def _reset_view(self) -> None:
        if self._hover_timer:
            self._hover_timer.stop()
            self._hover_timer = None
        self.query_one("#tile-poster").update("")
        
    async def _load_poster(self) -> None:
        if not self._is_active or not self.item_data.get("poster_path"): return
        self.remove_class("-hover-loading")
        poster_url = f"https://image.tmdb.org/t/p/w500{self.item_data['poster_path']}"
        
        # NEW: We save the worker task to the variable so we can control it
        self._render_worker = self.run_worker(self._fetch_and_render(poster_url, 28, 18))

    async def _fetch_and_render(self, url: str, width: int, height: int):
        poster_art, error = await self.api.get_poster_chafa(url, width=width, height=height)
        
        # Double check mouse state
        if not self._is_active or error or not poster_art:
            self._loading_poster = False
            return

        poster_widget = self.query_one("#tile-poster")
        # Strip trailing newlines to prevent layout jitter
        poster_widget.update(Text.from_ansi(poster_art.rstrip()))
        
        self.add_class("-show-poster")
        self._loading_poster = False
