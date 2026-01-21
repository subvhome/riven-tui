from textual.app import ComposeResult
from textual.widgets import Static, Label
from textual.containers import Vertical, Horizontal
from textual.message import Message
from textual import events
from rich.text import Text

HOVER_DELAY = 2.0 # Seconds to hover before loading poster

class SearchGridTile(Vertical):
    """A tile representing a media item in the search grid."""

    class Selected(Message):
        def __init__(self, item_data: dict) -> None:
            self.item_data = item_data
            super().__init__()

    def __init__(self, item_data: dict, api) -> None:
        super().__init__(classes="search-tile")
        self.item_data = item_data
        self.api = api
        self._hover_timer = None
        self._is_hovering = False # Track actual hover state

    def compose(self) -> ComposeResult:
        title = self.item_data.get('title') or self.item_data.get('name') or "Unknown"
        date = self.item_data.get('release_date') or self.item_data.get('first_air_date')
        year = date[:4] if date else "????"
        
        rating = self.item_data.get('vote_average', 0)
        rating_str = f"⭐ {rating:.1f}" if rating > 0 else ""
        
        state = self.item_data.get('state')
        state_str = state.title() if state else ""

        media_type = self.item_data.get('media_type', 'unknown').upper()
        type_icon = "🎬" if media_type == 'MOVIE' else "📺"

        # Container for the Poster (Hidden by default)
        yield Static(id="tile-poster", classes="hidden")

        # Container for Text Info (Visible by default)
        with Vertical(id="tile-info"):
            # Top Row: State and Rating
            with Horizontal(classes="tile-header"):
                yield Label(state_str, classes=f"tile-state state-{state.lower() if state else 'none'}")
                yield Label(rating_str, classes="tile-rating")

            # Middle: Title
            with Vertical(classes="tile-body"):
                yield Label(title, classes="tile-title")

            # Bottom: Icon + Year
            with Horizontal(classes="tile-footer"):
                yield Label(f"{type_icon} {media_type}", classes="tile-type")
                yield Label(year, classes="tile-year")

    def on_click(self) -> None:
        self.post_message(self.Selected(self.item_data))

    def on_enter(self, event: events.Enter) -> None:
        self._is_hovering = True
        self.add_class("-hover-loading")
        # Use constant for delay
        self._hover_timer = self.set_timer(HOVER_DELAY, self._load_poster)

    def on_leave(self, event: events.Leave) -> None:
        # Check if the mouse is still over the tile or one of its children
        mouse_pos = self.app.mouse_position
        try:
            widget, _ = self.app.get_widget_at(*mouse_pos)
            if widget is self or any(ancestor is self for ancestor in widget.ancestors):
                return
        except:
            pass

        self._is_hovering = False
        self.remove_class("-hover-loading")
        
        if self._hover_timer:
            self._hover_timer.stop()
            self._hover_timer = None
        
        # Always reset view to text only on leave
        self.query_one("#tile-poster").update("")
        self.query_one("#tile-poster").add_class("hidden")
        self.query_one("#tile-info").remove_class("hidden")
        self._poster_loaded = False

    async def _load_poster(self) -> None:
        if not self._is_hovering:
            return

        self.remove_class("-hover-loading")
        
        poster_path = self.item_data.get("poster_path")
        if not poster_path:
            return

        poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}"
        
        # Accounting for 1-cell padding in the tile (20 height -> 18 available)
        target_width = 28
        target_height = 18
        
        self.run_worker(self._fetch_and_render(poster_url, target_width, target_height))

    async def _fetch_and_render(self, url: str, width: int, height: int):
        # Double check we are still hovering before rendering
        if not self._is_hovering:
            return

        poster_art, error = await self.api.get_poster_chafa(url, width=width, height=height)
        
        # Triple check (async await might have taken time)
        if not self._is_hovering:
            return

        if error:
            # Optionally show error, but better to fail silent/graceful in grid
            return

        if poster_art:
            poster_widget = self.query_one("#tile-poster")
            poster_widget.update(Text.from_ansi(poster_art))
            
            # Swap views
            self.query_one("#tile-info").add_class("hidden")
            poster_widget.remove_class("hidden")