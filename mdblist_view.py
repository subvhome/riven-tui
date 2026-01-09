from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Static, Label, Button, Input, Log
from textual.message import Message
from textual import on
import asyncio

class MdblistView(Vertical):
    def compose(self) -> ComposeResult:
        yield Label("MDBLIST MASS MANAGER", classes="view-title")
        
        with Container(classes="mdblist-input-container"):
            yield Label("Enter Mdblist URL or ID:")
            yield Input(placeholder="e.g., https://mdblist.com/lists/user/my-list or just the ID", id="mdblist-input")
            yield Button("Fetch & Map", id="btn-mdblist-fetch", variant="primary")

        with Vertical(id="mdblist-results-container"):
            yield Label("Ready to scan...", id="mdblist-status-label")
            yield Log(id="mdblist-log", highlight=True)
        
        with Horizontal(id="mdblist-actions-row"):
            yield Button("Delete Matches", id="btn-mdblist-delete", variant="error", disabled=True)
            yield Button("Retry Matches", id="btn-mdblist-retry", variant="warning", disabled=True)
            yield Button("Reset Matches", id="btn-mdblist-reset", variant="warning", disabled=True)

    matched_riven_ids = []

    @on(Button.Pressed, "#btn-mdblist-fetch")
    async def on_fetch(self):
        list_input = self.query_one("#mdblist-input", Input).value.strip()
        if not list_input:
            self.query_one("#mdblist-log", Log).write_line("Error: Please enter a list ID or URL.")
            return

        self.query_one("#mdblist-fetch", Button).disabled = True
        log = self.query_one("#mdblist-log", Log)
        log.clear()
        log.write_line(f"Fetching Mdblist: {list_input}...")
        
        # 1. Fetch Mdblist
        api = self.app.api
        mdb_items, error = await api.get_mdblist_items(list_input)
        
        if error or not mdb_items:
            log.write_line(f"Error fetching Mdblist: {error}")
            self.query_one("#mdblist-fetch", Button).disabled = False
            return

        log.write_line(f"✅ Found {len(mdb_items)} items in Mdblist.")
        
        # 2. Fetch Riven Library
        log.write_line("Downloading full Riven library index (120s timeout)...")
        riven_key = self.app.settings.get("riven_key")
        lib_resp, lib_err = await api.get_items(riven_key, limit=999999, extended=False, timeout=120.0)
        
        if lib_err:
            log.write_line(f"Error fetching library: {lib_err}")
            self.query_one("#mdblist-fetch", Button).disabled = False
            return

        library_items = lib_resp.get("items", [])
        log.write_line(f"✅ Fetched {len(library_items)} items from Riven.")

        # 3. Build Map
        log.write_line("Building ID map...")
        riven_map = {}
        for item in library_items:
            rid = item.get("id")
            itype = item.get("type")
            
            # Map TMDB (Movies)
            tmdb = item.get("tmdb_id") or (item.get("parent_ids") or {}).get("tmdb_id")
            if tmdb:
                riven_map[(itype, str(tmdb))] = rid
            
            # Map TVDB (Shows)
            tvdb = item.get("tvdb_id") or (item.get("parent_ids") or {}).get("tvdb_id")
            if tvdb:
                riven_map[(itype, str(tvdb))] = rid

        # 4. Match
        self.matched_riven_ids = []
        for m_item in mdb_items:
            # Mdblist uses 'mediatype' (movie/show), Riven uses 'type' (movie/show)
            m_type = m_item.get("mediatype")
            
            # Try to match TMDB first (common for movies)
            m_tmdb = str(m_item.get("id")) # Mdblist ID is usually TMDB ID for movies
            
            # Try to match TVDB if available (Mdblist might provide it differently, usually 'id' is TMDB/TVDB depending)
            # Assuming 'id' is the primary external ID.
            
            key = (m_type, m_tmdb)
            
            if key in riven_map:
                self.matched_riven_ids.append(int(riven_map[key]))
                log.write_line(f"Match: {m_item.get('title')} -> ID {riven_map[key]}")

        match_count = len(self.matched_riven_ids)
        status_text = f"Found {match_count} matches out of {len(mdb_items)} list items."
        self.query_one("#mdblist-status-label", Label).update(status_text)
        log.write_line(f"🏁 {status_text}")

        if match_count > 0:
            self.query_one("#btn-mdblist-delete").disabled = False
            self.query_one("#btn-mdblist-retry").disabled = False
            self.query_one("#btn-mdblist-reset").disabled = False
        else:
            self.query_one("#btn-mdblist-delete").disabled = True
            self.query_one("#btn-mdblist-retry").disabled = True
            self.query_one("#btn-mdblist-reset").disabled = True
            
        self.query_one("#mdblist-fetch", Button).disabled = False

    async def run_bulk_action(self, action: str):
        if not self.matched_riven_ids:
            return

        api = self.app.api
        riven_key = self.app.settings.get("riven_key")
        log = self.query_one("#mdblist-log", Log)
        
        log.write_line(f"🚀 Executing BULK {action.upper()} on {len(self.matched_riven_ids)} items...")
        
        success = False
        msg = ""
        
        if action == "delete":
            success, msg = await api.bulk_delete_items(self.matched_riven_ids, riven_key)
        elif action == "retry":
            success, msg = await api.bulk_retry_items(self.matched_riven_ids, riven_key)
        elif action == "reset":
            success, msg = await api.bulk_reset_items(self.matched_riven_ids, riven_key)

        if success:
            log.write_line(f"✅ Bulk {action} successful!")
            self.query_one("#mdblist-status-label", Label).update(f"Action '{action}' complete.")
            # Clear lists to prevent double submission
            self.matched_riven_ids = []
            self.query_one("#btn-mdblist-delete").disabled = True
            self.query_one("#btn-mdblist-retry").disabled = True
            self.query_one("#btn-mdblist-reset").disabled = True
        else:
            log.write_line(f"❌ Bulk {action} failed: {msg}")

    @on(Button.Pressed, "#btn-mdblist-delete")
    async def on_delete(self):
        await self.run_bulk_action("delete")

    @on(Button.Pressed, "#btn-mdblist-retry")
    async def on_retry(self):
        await self.run_bulk_action("retry")

    @on(Button.Pressed, "#btn-mdblist-reset")
    async def on_reset(self):
        await self.run_bulk_action("reset")
