from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Static, Label, Button
from textual.message import Message
import asyncio

class DashboardView(Vertical):
    """The new Dashboard layout optimized for widget reuse."""

    class DashboardItem(Horizontal):
        """A clickable item in the dashboard lists."""
        can_focus = True
        BINDINGS = [
            ("enter", "select", "Select"),
        ]

        def __init__(self, label: str = "", item_data: dict = None, source: str = "", show_add: bool = False, **kwargs):
            super().__init__(classes="db-list-item-container hidden", **kwargs)
            self.label_text = label
            self.item_data = item_data
            self.source = source
            self.show_add = show_add

        def compose(self) -> ComposeResult:
            yield Label(self.label_text, id="item-label", classes="db-list-item-label")
            yield Button("[+]", id="btn-quick-add", classes="db-quick-add-btn hidden")

        def update_item(self, label: str, item_data: dict, source: str, show_add: bool):
            self.label_text = label
            self.item_data = item_data
            self.source = source
            self.show_add = show_add
            
            self.query_one("#item-label", Label).update(label)
            btn = self.query_one("#btn-quick-add", Button)
            btn.set_class(not show_add, "hidden")
            self.remove_class("hidden")

        class Clicked(Message):
            def __init__(self, item_data: dict, source: str):
                super().__init__()
                self.item_data = item_data
                self.source = source

        class QuickAdd(Message):
            def __init__(self, item_data: dict):
                super().__init__()
                self.item_data = item_data

        def action_select(self) -> None:
            if self.item_data:
                self.post_message(self.Clicked(self.item_data, self.source))

        def on_click(self, event) -> None:
            if not self.item_data: return
            if self.show_add:
                btn = self.query_one("#btn-quick-add", Button)
                if event.screen_x >= btn.region.x and event.screen_x < (btn.region.x + btn.region.width):
                    return
            self.post_message(self.Clicked(self.item_data, self.source))

        def on_button_pressed(self, event: Button.Pressed) -> None:
            if event.button.id == "btn-quick-add":
                event.stop()
                self.post_message(self.QuickAdd(self.item_data))
    
    def compose(self) -> ComposeResult:
        yield Horizontal(
            Label("Loading stats...", id="db-stats-label"),
            Label("API: UNKNOWN", id="db-health-label"),
            id="db-header"
        )
        with Horizontal(id="db-data-row"):
            with Vertical(id="db-tile-left-wrapper", classes="db-tile-wrapper"):
                with Horizontal(classes="db-tile-header"):
                    yield Label("RECENTLY ADDED")
                with Vertical(id="db-tile-left", classes="db-data-tile"):
                    for i in range(10):
                        yield self.DashboardItem(id=f"recent-{i}")
            
            with Vertical(id="db-tile-right-wrapper", classes="db-tile-wrapper"):
                with Horizontal(classes="db-tile-header"):
                    yield Label("TRENDING")
                    yield Label("REQ", classes="db-tile-header-req")
                with Vertical(id="db-tile-right", classes="db-data-tile"):
                    for i in range(10):
                        yield self.DashboardItem(id=f"trending-{i}")

        with Vertical(id="db-pills-frame"):
            with Vertical(id="db-service-pills"):
                # Pre-allocate pills for all potential services
                SERVICES = [
                    "OVERSEERR", "PLEX_WL", "LISTRR", "MDBLIST", "TRAKT",
                    "AIOSTREAMS", "COMET", "JACKETT", "MEDIAFUSION", "ORIONOID",
                    "PROWLARR", "RARBG", "TORRENTIO", "ZILEAN", "PLEX",
                    "JELLYFIN", "EMBY", "RD", "DEBRIDLINK", "ALLDEBRID"
                ]
                for s in SERVICES:
                    yield Static("", id=f"pill-{s.lower()}", classes="db-service-pill hidden")

        with Vertical(id="db-states-frame"):
            with Vertical(id="db-states-grid"):
                STATES = [
                    "Completed", "PartiallyCompleted", "Indexed", "Ongoing",
                    "Unreleased", "Unknown", "Paused", "Failed",
                    "Scraped", "Downloaded", "Symlinked", "Requested"
                ]
                for state in STATES:
                    with Vertical(id=f"state-tile-{state.lower()}", classes=f"db-state-tile state-{state.lower()} hidden"):
                        yield Label(state.upper(), classes="db-state-label")
                        yield Label("0", id=f"count-{state.lower()}", classes="db-state-count")

    def on_mount(self) -> None:
        self.query_one("#db-pills-frame").border_title = "SERVICE HEALTH"
        self.query_one("#db-states-frame").border_title = "LIBRARY STATES"

    def on_resize(self) -> None:
        if self.size.width < 100:
            self.add_class("-stacked")
        else:
            self.remove_class("-stacked")

    async def update_recently_added(self, items: list, ratings: dict = None):
        for i in range(10):
            widget = self.query_one(f"#recent-{i}", self.DashboardItem)
            if i < len(items):
                item = items[i]
                title = item.get("title") or "Unknown"
                aired_at = item.get("aired_at")
                year = f" ({aired_at[:4]})" if aired_at and len(aired_at) >= 4 else ""
                item_id = str(item.get("tmdb_id") or (item.get("parent_ids") or {}).get("tmdb_id") or item.get("tvdb_id") or "")
                
                rating_val = ratings.get(item_id, 0) if ratings else (item.get("vote_average") or 0)
                rating = f" [#D4AF37]{rating_val:.1f}[/]" if rating_val > 0 else ""
                icon = "🎬" if item.get("type") == "movie" else "📺"
                
                widget.update_item(f"{icon} {title}{year}{rating}", item, "library", False)
            else:
                widget.add_class("hidden")

    async def update_trending(self, items: list, library_status: dict = None):
        for i in range(10):
            widget = self.query_one(f"#trending-{i}", self.DashboardItem)
            if i < len(items):
                item = items[i]
                title = item.get("title") or item.get("name") or "Unknown"
                release_date = item.get("release_date") or item.get("first_air_date")
                year = f" ({release_date[:4]})" if release_date and len(release_date) >= 4 else ""
                rating_val = item.get("vote_average") or 0
                rating = f" [#D4AF37]{rating_val:.1f}[/]" if rating_val > 0 else ""
                icon = "🎬" if item.get("media_type") == "movie" else "📺"
                exists = library_status.get(str(item.get("id")), False) if library_status else False
                
                widget.update_item(f"{icon} {title}{year}{rating}", item, "trending", not exists)
            else:
                widget.add_class("hidden")

    async def update_service_pills(self, services: dict, settings: dict):
        SERVICE_MAP = {
            "overseerr": "content.overseerr.enabled", "plex_watchlist": "content.plex_watchlist.enabled",
            "listrr": "content.listrr.enabled", "mdblist": "content.mdblist.enabled",
            "trakt": "content.trakt.enabled", "aiostreams": "scraping.aiostreams.enabled",
            "comet": "scraping.comet.enabled", "jackett": "scraping.jackett.enabled",
            "mediafusion": "scraping.mediafusion.enabled", "orionoid": "scraping.orionoid.enabled",
            "prowlarr": "scraping.prowlarr.enabled", "rarbg": "scraping.rarbg.enabled",
            "torrentio": "scraping.torrentio.enabled", "zilean": "scraping.zilean.enabled",
            "plexupdater": "updaters.plex.enabled", "jellyfin": "updaters.jellyfin.enabled",
            "emby": "updaters.emby.enabled", "realdebrid": "downloaders.real_debrid.enabled",
            "debridlink": "downloaders.debrid_link.enabled", "alldebrid": "downloaders.all_debrid.enabled"
        }

        def get_nested(data, path):
            parts = path.split(".")
            for p in parts:
                if isinstance(data, dict): data = data.get(p)
                else: return None
            return data

        for s_name, s_path in SERVICE_MAP.items():
            is_enabled = get_nested(settings, s_path) is True
            is_healthy = services.get(s_name) is True
            status = "disabled"
            if is_enabled: status = "healthy" if is_healthy else "unhealthy"
            
            p_id = s_name.replace("watchlist", "wl").replace("realdebrid", "rd").replace("plexupdater", "plex")
            try:
                pill = self.query_one(f"#pill-{p_id}", Static)
                display_name = p_id.upper()
                if status == "healthy": content = f"[#6A994E]●[/] {display_name}"
                elif status == "unhealthy": content = f"[#E57373]● {display_name}[/]"
                else: content = f"  {display_name}"
                
                pill.update(content)
                pill.set_classes(f"db-service-pill pill-{status}")
            except: pass

    async def update_states_overview(self, states: dict):
        order = ["Completed", "PartiallyCompleted", "Indexed", "Ongoing", "Unreleased", "Unknown", "Paused", "Failed", "Scraped", "Downloaded", "Symlinked", "Requested"]
        for state in order:
            try:
                tile = self.query_one(f"#state-tile-{state.lower()}", Vertical)
                count_label = self.query_one(f"#count-{state.lower()}", Label)
                count = states.get(state, 0)
                count_label.update(str(count))
                tile.remove_class("hidden")
            except: pass

    async def update_stats(self, stats: dict, health_ok: bool):
        stats_label = self.query_one("#db-stats-label", Label)
        health_label = self.query_one("#db-health-label", Label)
        movies = stats.get("total_movies", 0)
        shows = stats.get("total_shows", 0)
        episodes = stats.get("total_episodes", 0)
        stats_label.update(f"🎬 [bold]{movies}[/] Movies   📺 [bold]{shows}[/] Shows   🎬 [bold]{episodes}[/] Episodes")
        health_label.update("API: [bold green]ONLINE[/]" if health_ok else "API: [bold red]OFFLINE[/]")
