from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Static, Label, Button, Input, Log, ListView, ListItem
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
        status.update("[yellow]Fetching list and mapping library...[/]")
        self.app.log_message(f"Advanced: Starting scan for {val}")
        
        matched_list = self.query_one("#adv-matched-list", ListView)
        matched_list.clear()

        # 1. Fetch Mdblist
        mdb_items, mdb_err = await self.app.api.get_mdblist_items(val)
        if mdb_err:
            status.update(f"[red]Mdblist Error: {mdb_err}[/]")
            self.app.log_message(f"Advanced: Mdblist Error: {mdb_err}")
            return

        self.app.log_message(f"Advanced: Mdblist returned {len(mdb_items.get('movies', [])) + len(mdb_items.get('shows', []))} items.")

        # 2. Big Gulp - Fetch whole library index
        riven_key = self.app.settings.get("riven_key")
        self.app.log_message("Advanced: Requesting full Riven library index...")
        lib_resp, lib_err = await self.app.api.get_items(riven_key, limit=999999, extended=False)
        
        if lib_err or lib_resp is None:
            error_msg = lib_err or "Unknown API Error (No data returned from Riven)"
            status.update(f"[red]Riven Error: {error_msg}[/]")
            self.app.log_message(f"Advanced: Riven Fetch Error: {error_msg}")
            self.query_one("#btn-adv-scan", Button).disabled = False
            return

        library_items = lib_resp.get("items", [])
        
        # 3. Build Multi-ID Lookup Map (Including Title)
        riven_map = {}
        for item in library_items:
            rid = item.get("id")
            itype = item.get("type")
            title = item.get("title", "Unknown")
            
            entry = {"id": rid, "title": title}
            
            # Map TMDB
            tmdb = item.get("tmdb_id") or (item.get("parent_ids") or {}).get("tmdb_id")
            if tmdb: riven_map[(itype, "tmdb", str(tmdb))] = entry
            
            # Map TVDB
            tvdb = item.get("tvdb_id") or (item.get("parent_ids") or {}).get("tvdb_id")
            if tvdb: riven_map[(itype, "tvdb", str(tvdb))] = entry

            # Map IMDB (Crucial for Movies)
            imdb = item.get("imdb_id") or (item.get("parent_ids") or {}).get("imdb_id")
            if imdb: riven_map[(itype, "imdb", str(imdb))] = entry

        # 4. Cross-Reference using multiple fallback IDs
        self.matched_ids = []
        unique_matches = set()
        matched_titles = []
        
        def add_match(entry):
            if entry["id"] not in unique_matches:
                unique_matches.add(entry["id"])
                self.matched_ids.append(str(entry["id"]))
                matched_titles.append(entry["title"])

        # Process Movies
        for m in mdb_items.get("movies", []):
            m_id = str(m.get("id")) # Usually TMDB
            m_imdb = str(m.get("imdb_id"))
            
            if ("movie", "tmdb", m_id) in riven_map: add_match(riven_map[("movie", "tmdb", m_id)])
            elif ("movie", "imdb", m_imdb) in riven_map: add_match(riven_map[("movie", "imdb", m_imdb)])

        # Process Shows
        for s in mdb_items.get("shows", []):
            s_tvdb = str(s.get("tvdb_id"))
            s_imdb = str(s.get("imdb_id"))
            s_id = str(s.get("id"))
            
            if ("show", "tvdb", s_tvdb) in riven_map: add_match(riven_map[("show", "tvdb", s_tvdb)])
            elif ("show", "imdb", s_imdb) in riven_map: add_match(riven_map[("show", "imdb", s_imdb)])
            elif ("show", "tmdb", s_id) in riven_map: add_match(riven_map[("show", "tmdb", s_id)])

        # 5. Update UI
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
        
        # Log to the internal app log too
        self.app.log_message(f"Advanced: Executing {action} on IDs: {self.matched_ids}")
        
        riven_key = self.app.settings.get("riven_key")
        success, msg = await self.app.api.bulk_action(action, self.matched_ids, riven_key)
        
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