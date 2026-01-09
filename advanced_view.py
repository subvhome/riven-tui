from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Static, Label, Button, Input, Log, ListView, ListItem
from textual import on
from typing import List
import asyncio

class AdvancedView(Vertical):
    matched_ids: List[str] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="advanced-container"):
            yield Label("MDBLIST MASS MANAGER (Enter ID or URL)", classes="advanced-label")
            
            with Horizontal(classes="advanced-row"):
                yield Input(placeholder="Paste Mdblist ID here...", id="adv-mdblist-input")
                yield Button("Scan Library", id="btn-adv-scan", variant="primary")

            yield Static("", id="adv-status-line", classes="advanced-status")

            with Vertical(id="adv-matched-container", classes="advanced-scroll-box"):
                yield Label("MATCHED TITLES", classes="advanced-sub-label")
                yield ListView(id="adv-matched-list")

            with Horizontal(classes="advanced-row", id="adv-actions-row"):
                yield Button("Mass Delete", id="btn-adv-delete", variant="error", disabled=True)
                yield Button("Mass Reset", id="btn-adv-reset", variant="warning", disabled=True)
                yield Button("Mass Retry", id="btn-adv-retry", variant="primary", disabled=True)

            yield Static("─" * 40, classes="advanced-sep")
            
            yield Label("TRAKT.TV INTEGRATION", classes="advanced-label")
            with Horizontal(classes="advanced-row"):
                yield Button("Connect Trakt", id="btn-trakt-auth", disabled=True)
                yield Label("(Disabled - Placeholder)", classes="advanced-hint")

    @on(Button.Pressed, "#btn-adv-scan")
    async def on_scan(self) -> None:
        val = self.query_one("#adv-mdblist-input", Input).value.strip()
        if not val:
            self.query_one("#adv-status-line", Static).update("[red]Error: Input is empty[/]")
            return

        status = self.query_one("#adv-status-line", Static)
        status.update("[yellow]Fetching list from Mdblist...[/]")
        self.app.log_message(f"Advanced: Starting scan for {val}")
        
        matched_list = self.query_one("#adv-matched-list", ListView)
        matched_list.clear()

        # 1. Fetch Mdblist
        mdb_items, mdb_err = await self.app.api.get_mdblist_items(val)
        if mdb_err:
            status.update(f"[red]Mdblist Error: {mdb_err}[/]")
            self.app.log_message(f"Advanced: Mdblist Error: {mdb_err}")
            return

        all_mdb_items = mdb_items.get("movies", []) + mdb_items.get("shows", [])
        self.app.log_message(f"Advanced: Mdblist returned {len(all_mdb_items)} items.")
        
        if not all_mdb_items:
            status.update("[yellow]Mdblist is empty or not yet populated.[/]")
            return

        # 2. Surgical Probing - Query Riven for each specific ID in parallel
        status.update(f"[yellow]Surgically probing Riven for {len(all_mdb_items)} items...[/]")
        riven_key = self.app.settings.get("riven_key")
        self.matched_ids = []
        matched_titles = []
        
        # Concurrency control
        semaphore = asyncio.Semaphore(10)

        async def probe_movie(m):
            imdb_id = m.get("imdb_id")
            if not imdb_id: return None
            async with semaphore:
                resp, err = await self.app.api.get_items(riven_key, search=imdb_id, limit=1)
                if resp and resp.get("total_items", 0) > 0:
                    return resp["items"][0]
            return None

        async def probe_show(s):
            tvdb_id = s.get("tvdb_id")
            if not tvdb_id: return None
            async with semaphore:
                # Search by TVDB ID
                resp, err = await self.app.api.get_items(riven_key, search=str(tvdb_id), limit=1)
                if resp and resp.get("total_items", 0) > 0:
                    return resp["items"][0]
            return None

        # Create specific tasks for movies and shows
        tasks = []
        for m in mdb_items.get("movies", []):
            tasks.append(probe_movie(m))
        for s in mdb_items.get("shows", []):
            tasks.append(probe_show(s))

        # Execute all probes in parallel
        results = await asyncio.gather(*tasks)

        # 3. Process Results
        unique_matches = set()
        for item in results:
            if item and item.get("id") not in unique_matches:
                self.matched_ids.append(str(item["id"]))
                unique_matches.add(item["id"])
                matched_titles.append(item.get("title", "Unknown"))

        # 4. Update UI
        count = len(self.matched_ids)
        status.update(f"[green]Scan Complete: Found {count} matches in your library.[/]")
        
        for title in sorted(matched_titles):
            matched_list.append(ListItem(Label(title)))

        has_matches = count > 0
        self.query_one("#btn-adv-delete", Button).disabled = not has_matches
        self.query_one("#btn-adv-reset", Button).disabled = not has_matches
        self.query_one("#btn-adv-retry", Button).disabled = not has_matches

    async def run_action(self, action: str):
        if not self.matched_ids: return
        
        status = self.query_one("#adv-status-line", Static)
        status.update(f"[yellow]Sending {len(self.matched_ids)} IDs to Riven...[/]")
        
        self.app.log_message(f"Advanced: Executing {action} on IDs: {self.matched_ids}")
        
        riven_key = self.app.settings.get("riven_key")
        success, msg = await self.app.api.bulk_action(action, self.matched_ids, riven_key)
        
        if success:
            status.update(f"[bold green]Success: Bulk {action} completed for {len(self.matched_ids)} items.[/]")
            self.matched_ids = []
            self.query_one("#btn-adv-delete", Button).disabled = True
            self.query_one("#btn-adv-reset", Button).disabled = True
            self.query_one("#btn-adv-retry", Button).disabled = True
            self.query_one("#adv-matched-list", ListView).clear()
        else:
            status.update(f"[red]Action failed: {msg}[/]")

    @on(Button.Pressed, "#btn-adv-delete")
    async def on_delete(self): await self.run_action("remove")

    @on(Button.Pressed, "#btn-adv-reset")
    async def on_reset(self): await self.run_action("reset")

    @on(Button.Pressed, "#btn-adv-retry")
    async def on_retry(self): await self.run_action("retry")
