from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Static, Label, Button
from textual.message import Message
import asyncio

class DashboardView(Vertical):
    """The new Dashboard layout."""

    class DashboardItem(Horizontal):
        """A clickable item in the dashboard lists."""
        def __init__(self, label: str, item_data: dict, source: str, show_add: bool = False):
            super().__init__(classes="db-list-item-container")
            self.label_text = label
            self.item_data = item_data
            self.source = source
            self.show_add = show_add

        def compose(self) -> ComposeResult:
            yield Label(self.label_text, classes="db-list-item-label")
            if self.show_add:
                yield Button("[+]", id="btn-quick-add", classes="db-quick-add-btn")

        class Clicked(Message):
            def __init__(self, item_data: dict, source: str):
                super().__init__()
                self.item_data = item_data
                self.source = source

        class QuickAdd(Message):
            def __init__(self, item_data: dict):
                super().__init__()
                self.item_data = item_data

        def on_click(self, event) -> None:
            # If the [+] button was clicked, we ignore it here (handled by on_button_pressed)
            if self.show_add:
                btn = self.query_one(Button)
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
                yield Static("RECENTLY ADDED", id="db-tile-left-header", classes="db-tile-header")
                yield Vertical(id="db-tile-left", classes="db-data-tile")
            
            with Vertical(id="db-tile-right-wrapper", classes="db-tile-wrapper"):
                yield Static("TRENDING", id="db-tile-right-header", classes="db-tile-header")
                yield Vertical(id="db-tile-right", classes="db-data-tile")
        with Vertical(id="db-pills-frame"):
            yield Vertical(id="db-service-pills")
        with Vertical(id="db-states-frame"):
            yield Vertical(id="db-states-grid")

    def on_mount(self) -> None:
        self.query_one("#db-pills-frame").border_title = "SERVICE HEALTH"
        self.query_one("#db-states-frame").border_title = "LIBRARY STATES"

    def on_resize(self) -> None:
        """Handle responsive stacking of tiles."""
        if self.size.width < 100:
            self.add_class("-stacked")
        else:
            self.remove_class("-stacked")

    async def update_recently_added(self, items: list):
        """Update the left tile with recently added items."""
        tile = self.query_one("#db-tile-left", Vertical)
        await tile.query("*").remove()
        
        for item in items:
            title = item.get("title") or "Unknown"
            aired_at = item.get("aired_at")
            year = ""
            if aired_at and len(aired_at) >= 4:
                year = f" ({aired_at[:4]})"
            
            media_type = item.get("type", "movie")
            icon = "🎞️ " if media_type == "movie" else "📺"
            
            await tile.mount(self.DashboardItem(f"{icon} {title}{year}", item, source="library", show_add=False))

    async def update_trending(self, items: list, library_status: dict = None):
        """Update the right tile with trending items."""
        tile = self.query_one("#db-tile-right", Vertical)
        await tile.query("*").remove()
        
        for item in items[:10]: # Limit to 10
            title = item.get("title") or item.get("name") or "Unknown"
            release_date = item.get("release_date") or item.get("first_air_date")
            year = ""
            if release_date and len(release_date) >= 4:
                year = f" ({release_date[:4]})"
            
            media_type = item.get("media_type", "movie")
            icon = "🎞️ " if media_type == "movie" else "📺"
            
            tmdb_id = str(item.get("id"))
            # Check if this item is in library
            exists = False
            if library_status and tmdb_id in library_status:
                exists = library_status[tmdb_id]
            
            await tile.mount(self.DashboardItem(f"{icon} {title}{year}", item, source="trending", show_add=not exists))

    async def update_service_pills(self, services: dict, settings: dict):
        """Update the service pills bar based on health and settings."""
        container = self.query_one("#db-service-pills", Vertical)
        await container.query("*").remove()
        
        SERVICE_MAP = {
            "overseerr": "content.overseerr.enabled",
            "plex_watchlist": "content.plex_watchlist.enabled",
            "listrr": "content.listrr.enabled",
            "mdblist": "content.mdblist.enabled",
            "trakt": "content.trakt.enabled",
            "aiostreams": "scraping.aiostreams.enabled",
            "comet": "scraping.comet.enabled",
            "jackett": "scraping.jackett.enabled",
            "mediafusion": "scraping.mediafusion.enabled",
            "orionoid": "scraping.orionoid.enabled",
            "prowlarr": "scraping.prowlarr.enabled",
            "rarbg": "scraping.rarbg.enabled",
            "torrentio": "scraping.torrentio.enabled",
            "zilean": "scraping.zilean.enabled",
            "plexupdater": "updaters.plex.enabled",
            "jellyfin": "updaters.jellyfin.enabled",
            "emby": "updaters.emby.enabled",
            "realdebrid": "downloaders.real_debrid.enabled",
            "debridlink": "downloaders.debrid_link.enabled",
            "alldebrid": "downloaders.all_debrid.enabled"
        }

        def get_nested(data, path):
            parts = path.split(".")
            for p in parts:
                if isinstance(data, dict):
                    data = data.get(p)
                else:
                    return None
            return data

        pill_data = []
        for s_name, s_path in SERVICE_MAP.items():
            is_enabled = get_nested(settings, s_path) is True
            is_healthy = services.get(s_name) is True
            
            status = "disabled"
            if is_enabled:
                status = "healthy" if is_healthy else "unhealthy"
            
            # Display name: short versions for common ones
            display_name = s_name.replace("watchlist", "wl").replace("realdebrid", "rd").replace("plexupdater", "plex")
            
            pill_data.append({
                "name": display_name.upper(),
                "status": status,
                "priority": 0 if status == "unhealthy" else (1 if status == "healthy" else 2)
            })

        # Sort: unhealthy, healthy, disabled
        pill_data.sort(key=lambda x: x["priority"])

        for pill in pill_data:
            name = pill["name"]
            status = pill["status"]
            
            if status == "healthy":
                content = f"[#6A994E]●[/] {name}"
            elif status == "unhealthy":
                content = f"[#E57373]● {name}[/]"
            else: # disabled
                content = f"  {name}"
                
            p_class = f"pill-{status}"
            await container.mount(Static(content, classes=f"db-service-pill {p_class}"))

    async def update_states_overview(self, states: dict):
        """Update the grid with counts for each library state."""
        container = self.query_one("#db-states-grid", Vertical)
        await container.query("*").remove()
        
        # Consistent order for states
        order = [
            "Completed", "PartiallyCompleted", "Indexed", "Ongoing",
            "Unreleased", "Unknown", "Paused", "Failed",
            "Scraped", "Downloaded", "Symlinked", "Requested"
        ]
        
        for state in order:
            count = states.get(state, 0)
            # Create a tile for each state
            tile = Vertical(
                Label(state.upper(), classes="db-state-label"),
                Label(str(count), classes="db-state-count"),
                classes=f"db-state-tile state-{state.lower()}"
            )
            await container.mount(tile)

    async def update_stats(self, stats: dict, health_ok: bool):
        """Update the header with library counts and health status."""
        stats_label = self.query_one("#db-stats-label", Label)
        health_label = self.query_one("#db-health-label", Label)
        
        movies = stats.get("total_movies", 0)
        shows = stats.get("total_shows", 0)
        episodes = stats.get("total_episodes", 0)
        
        stats_label.update(f"🎬 [bold]{movies}[/] Movies   📺 [bold]{shows}[/] Shows   🎞️ [bold]{episodes}[/] Episodes")
        
        if health_ok:
            health_label.update("API: [bold green]ONLINE[/]")
        else:
            health_label.update("API: [bold red]OFFLINE[/]")
