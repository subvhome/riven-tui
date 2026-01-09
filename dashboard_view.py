from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Static, Label, ListView, ListItem, Button
from textual.message import Message
from textual import on
from typing import List, Dict
import asyncio
import logging
from rich.text import Text
from rich.align import Align

SERVICE_NAMES = {
    "overseerr": "Overseerr", "plex_watchlist": "Plex Watchlist", "listrr": "Listrr",
    "mdblist": "MdbList", "trakt": "Trakt", "indexer": "Indexer", "comet": "Comet",
    "jackett": "Jackett", "mediafusion": "MediaFusion", "orionoid": "Orionoid",
    "prowlarr": "Prowlarr", "rarbg": "RARBG", "torrentio": "Torrentio",
    "zilean": "Zilean", "plexupdater": "Plex Updater", "jellyfin": "Jellyfin",
    "emby": "Emby", "realdebrid": "Real-Debrid", "debridlink": "Debrid-Link",
    "alldebrid": "AllDebrid", "filesystem": "File System", "subtitle": "Subtitles",
    "notifications": "Notifications"
}

class DashboardItemClicked(Message):
    def __init__(self, item_data: dict, media_type: str = "tmdb") -> None:
        super().__init__()
        self.item_data = item_data
        self.media_type = media_type

class TrendingPageChanged(Message):
    def __init__(self, delta: int) -> None:
        super().__init__()
        self.delta = delta

class RefreshSystemStatus(Message):
    pass

class DashboardView(Vertical):
    def compose(self) -> ComposeResult:
        with Vertical(id="dashboard-content-wrapper"):
            with Vertical(id="dashboard-header-container"):
                yield Static("━━━━━━━━━━━━━━━━━━━━ DASHBOARD ━━━━━━━━━━━━━━━━━━━━", classes="dashboard-header-line")
                yield Static(" 🎞️ 0 Movies   📺 0 Shows   ✅ API Status: Checking...", id="dashboard-stats-line")
                yield Static("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", classes="dashboard-header-line")
            
            with Horizontal(id="dashboard-main-content"):
                with Vertical(id="dashboard-recent-col", classes="dashboard-column"):
                    yield Label("RECENTLY ADDED", classes="dashboard-section-title")
                    yield Label("──────────────────────────────", classes="dashboard-section-sep")
                    yield ListView(id="list-recent-added")

                with Vertical(id="dashboard-trending-col", classes="dashboard-column"):
                    with Horizontal(classes="dashboard-section-header-row"):
                        yield Label("TRENDING", classes="dashboard-section-title")
                        yield Button("<", id="btn-trending-prev", classes="dashboard-nav-btn")
                        yield Button(">", id="btn-trending-next", classes="dashboard-nav-btn")
                    yield Label("──────────────────────────────", classes="dashboard-section-sep")
                    yield ListView(id="list-trending")

                with Vertical(id="dashboard-status-col", classes="dashboard-column"):
                    with Horizontal(classes="dashboard-section-header-row"):
                        yield Label("SYSTEM STATUS", classes="dashboard-section-title")
                        yield Button("↻", id="btn-refresh-status", classes="dashboard-nav-btn")
                    yield Label("──────────────", classes="dashboard-section-sep")
                    with Vertical(id="status-items-container"):
                        pass

            # Custom Unicode Bar Chart Row
            with Vertical(id="dashboard-graph-row"):
                yield Label("LIBRARY STATE", classes="dashboard-section-title")
                yield Static(id="custom-bar-chart")

    async def update_stats(self, stats: dict, status: str):
        color = "green" if status.lower() == "online" else "red"
        movies = stats.get("total_movies", 0) if stats else 0
        shows = stats.get("total_shows", 0) if stats else 0
        stats_msg = f" 🎞️ {movies:,} Movies   📺 {shows:,} Shows   ✅ API Status: [{color}]{status}[/]"
        self.query_one("#dashboard-stats-line", Static).update(stats_msg)
        
        if stats:
            await self.update_graphs(stats)

    async def update_graphs(self, stats: dict):
        states_data = stats.get("states", {})
        active_states = {k: v for k, v in states_data.items() if v > 0}
        if not active_states: return

        sorted_states = sorted(active_states.items(), key=lambda x: x[1], reverse=True)
        
        max_bar_height = 10 
        max_val = max(active_states.values())
        
        lines = []
        col_data = []
        for _, val in sorted_states:
            h = int((val / max_val) * (max_bar_height - 1))
            col_data.append({"val": val, "bar_h": h})

        for r in range(max_bar_height, -1, -1):
            row_str = ""
            for col in col_data:
                if r == col["bar_h"] + 1:
                    row_str += f"[bold white]{col['val']:^12}[/]"
                elif r <= col["bar_h"] and col["bar_h"] > 0:
                    row_str += "    [#3D5A80]████[/]    "
                elif r == 0 and col["bar_h"] == 0:
                    row_str += "    [#3D5A80]▆▆▆▆[/]    "
                else:
                    row_str += "            "
            lines.append(row_str)

        label_line = ""
        for label, _ in sorted_states:
            display_label = (label[:10] + '..') if len(label) > 10 else label
            label_line += f"{display_label:^12}"
        lines.append(f"[grey]{label_line}[/]")

        # Wrap in Align.center to force the block to the middle of the dashboard
        final_chart = Align.center(Text.from_markup("\n".join(lines)))
        self.query_one("#custom-bar-chart", Static).update(final_chart)

    async def update_services(self, services: dict, enabled_keys: List[str]):
        container = self.query_one("#status-items-container", Vertical)
        await container.query("*").remove()
        for key in enabled_keys:
            name = SERVICE_NAMES.get(key, key.capitalize())
            is_ok = services.get(key, False)
            status_text = "[green]OK[/]" if is_ok else "[red]ERR[/]"
            await container.mount(Label(f"{name}: {status_text}"))

    async def update_recent(self, items: List[dict]):
        lv = self.query_one("#list-recent-added", ListView)
        lv.clear()
        for item in items[:5]:
            title = item.get("title", "Unknown")
            year = f" ({item['aired_at'][:4]})" if item.get("aired_at") else ""
            icon = "🎬" if item.get("type") == "movie" else "📺"
            li = ListItem(Label(f"{icon} {title}{year}"), classes="dashboard-list-item")
            li.item_data = item
            li.source_type = "riven"
            lv.append(li)

    async def update_trending(self, items: List[dict], page: int = 1):
        lv = self.query_one("#list-trending", ListView)
        lv.clear()
        if not items:
            return

        for i, item in enumerate(items[:10], 1):
            title = item.get("title") or item.get("name") or "Unknown"
            icon = "🎬" if item.get("media_type") == "movie" else "📺"
            display_num = ((page - 1) * 10) + i
            li = ListItem(Label(f"{display_num}. {icon} {title}"), classes="dashboard-list-item")
            li.item_data = item
            li.source_type = "tmdb"
            lv.append(li)

    @on(Button.Pressed, "#btn-refresh-status")
    def on_refresh_status(self):
        self.post_message(RefreshSystemStatus())

    @on(Button.Pressed, "#btn-trending-prev")
    def on_prev_page(self):
        self.post_message(TrendingPageChanged(-1))

    @on(Button.Pressed, "#btn-trending-next")
    def on_next_page(self):
        self.post_message(TrendingPageChanged(1))

    @on(ListView.Selected)
    def on_item_selected(self, event: ListView.Selected):
        if hasattr(event.item, "item_data"):
            self.post_message(DashboardItemClicked(event.item.item_data, event.item.source_type))