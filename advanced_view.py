from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Static, Label, Button, Input, Log
from textual import on
from typing import List

class AdvancedView(Vertical):
    matched_ids: List[str] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="advanced-container"):
            yield Label("MDBLIST MASS MANAGER (Enter ID or URL)", classes="advanced-label")
            
            with Horizontal(classes="advanced-row"):
                yield Input(placeholder="Paste Mdblist ID here...", id="adv-mdblist-input")
                yield Button("Scan Library", id="btn-adv-scan", variant="primary")

            yield Static("", id="adv-status-line", classes="advanced-status")

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
        status.update("[yellow]Fetching list and mapping library...[/]")
        
        # 1. Fetch Mdblist
        mdb_items, mdb_err = await self.app.api.get_mdblist_items(val)
        if mdb_err:
            status.update(f"[red]Mdblist Error: {mdb_err}[/]")
            return

        # 2. Big Gulp - Fetch whole library index
        api_key = self.app.settings.get("api_key")
        lib_resp, lib_err = await self.app.api.get_items(api_key, limit=999999, extended=False)
        if lib_err:
            status.update(f"[red]Riven Error: {lib_err}[/]")
            return

        library_items = lib_resp.get("items", [])
        
        # 3. Build Multi-ID Lookup Map
        riven_map = {}
        for item in library_items:
            rid = item.get("id")
            itype = item.get("type")
            
            # Map TMDB
            tmdb = item.get("tmdb_id") or (item.get("parent_ids") or {}).get("tmdb_id")
            if tmdb: riven_map[(itype, "tmdb", str(tmdb))] = rid
            
            # Map TVDB
            tvdb = item.get("tvdb_id") or (item.get("parent_ids") or {}).get("tvdb_id")
            if tvdb: riven_map[(itype, "tvdb", str(tvdb))] = rid

            # Map IMDB (Crucial for Movies)
            imdb = item.get("imdb_id") or (item.get("parent_ids") or {}).get("imdb_id")
            if imdb: riven_map[(itype, "imdb", str(imdb))] = rid

        # 4. Cross-Reference using multiple fallback IDs
        self.matched_ids = []
        unique_matches = set()
        
        # Process Movies
        for m in mdb_items.get("movies", []):
            m_id = str(m.get("id")) # Usually TMDB
            m_imdb = str(m.get("imdb_id"))
            
            match_id = None
            if ("movie", "tmdb", m_id) in riven_map: match_id = riven_map[("movie", "tmdb", m_id)]
            elif ("movie", "imdb", m_imdb) in riven_map: match_id = riven_map[("movie", "imdb", m_imdb)]
            
            if match_id and match_id not in unique_matches:
                self.matched_ids.append(str(match_id))
                unique_matches.add(match_id)

        # Process Shows
        for s in mdb_items.get("shows", []):
            s_tvdb = str(s.get("tvdb_id"))
            s_imdb = str(s.get("imdb_id"))
            s_id = str(s.get("id"))
            
            match_id = None
            if ("show", "tvdb", s_tvdb) in riven_map: match_id = riven_map[("show", "tvdb", s_tvdb)]
            elif ("show", "imdb", s_imdb) in riven_map: match_id = riven_map[("show", "imdb", s_imdb)]
            elif ("show", "tmdb", s_id) in riven_map: match_id = riven_map[("show", "tmdb", s_id)]
            
            if match_id and match_id not in unique_matches:
                self.matched_ids.append(str(match_id))
                unique_matches.add(match_id)

        # 5. Update UI
        count = len(self.matched_ids)
        status.update(f"[green]Scan Complete: Found {count} matches in your library.[/]")
        
        has_matches = count > 0
        self.query_one("#btn-adv-delete", Button).disabled = not has_matches
        self.query_one("#btn-adv-reset", Button).disabled = not has_matches
        self.query_one("#btn-adv-retry", Button).disabled = not has_matches

    async def run_action(self, action: str):
        if not self.matched_ids: return
        
        status = self.query_one("#adv-status-line", Static)
        status.update(f"[yellow]Executing bulk {action} on {len(self.matched_ids)} items...[/]")
        
        api_key = self.app.settings.get("api_key")
        success, msg = await self.app.api.bulk_action(action, self.matched_ids, api_key)
        
        if success:
            status.update(f"[bold green]Success: Bulk {action} completed for {len(self.matched_ids)} items.[/]")
            self.matched_ids = []
            self.query_one("#btn-adv-delete", Button).disabled = True
            self.query_one("#btn-adv-reset", Button).disabled = True
            self.query_one("#btn-adv-retry", Button).disabled = True
        else:
            status.update(f"[red]Action failed: {msg}[/]")

    @on(Button.Pressed, "#btn-adv-delete")
    async def on_delete(self): await self.run_action("remove")

    @on(Button.Pressed, "#btn-adv-reset")
    async def on_reset(self): await self.run_action("reset")

    @on(Button.Pressed, "#btn-adv-retry")
    async def on_retry(self): await self.run_action("retry")