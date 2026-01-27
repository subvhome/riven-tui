from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Static, Label, Button, Input, Log, ListView, ListItem
from textual import on
from typing import List
import asyncio
from modals import ConfirmationScreen

from textual.reactive import reactive

class AdvancedView(Vertical):
    matched_ids: List[str] = []
    show_mdblist = reactive(False)
    show_import_export = reactive(False)

    def compose(self) -> ComposeResult:
        with Vertical(id="advanced-container"):
            # 1. MDBList Section
            yield Static("MDBList Bulk Manager ▶", id="mdblist-header", classes="advanced-header-toggle")
            
            with Vertical(id="mdblist-bulk-area", classes="bulk-area-panel"):
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

            # 2. Import/Export Section
            yield Static("Import/Export Library ▶", id="import-export-header", classes="advanced-header-toggle")
            
            with Vertical(id="import-export-area", classes="bulk-area-panel"):
                with Horizontal(classes="advanced-row"):
                    yield Button("Export Library", id="btn-export-lib", variant="primary")
                    yield Button("Import Library", id="btn-import-lib", variant="success")
                
                yield Static("", id="export-status", classes="advanced-status")
                yield Static("") # Blank line spacer
                
                yield Label("Usage Notes:", classes="advanced-sub-label")
                yield Label(
                    "• [bold]Export[/]: Saves IDs to [cyan]riven_export.json[/]\n"
                    "• [bold]Migration[/]: Move file to new instance folder\n"
                    "• [bold]Import[/]: Requests all items from file",
                    classes="advanced-hint"
                )

    @on(Button.Pressed, "#btn-import-lib")
    def on_import_click(self) -> None:
        self.run_worker(self.perform_import())

    async def perform_import(self) -> None:
        status = self.query_one("#export-status", Static)
        import os
        import json
        
        file_path = "riven_export.json"
        if not os.path.exists(file_path):
            status.update(f"[red]Error: {file_path} not found.[/]")
            return

        # 1. Ask for confirmation
        confirmed = await self.app.push_screen_wait(ConfirmationScreen(
            "Import Library",
            f"Are you sure you want to import items from [cyan]{file_path}[/]?\n\nExisting items will be automatically skipped.",
            confirm_label="Yes, Import",
            variant="success"
        ))
        
        if not confirmed:
            return

        riven_key = self.app.settings.get("riven_key")
        
        # 2. Sync existing library IDs to avoid duplicates
        status.update("[yellow]Syncing current library state...[/]")
        existing_ids = set() # Store as strings for easy matching
        
        limit = 500
        resp, err = await self.app.api.get_items(riven_key, limit=1)
        if resp:
            total_items = resp.get("total_items", 0)
            total_pages = (total_items + limit - 1) // limit
            for page in range(1, total_pages + 1):
                status.update(f"[yellow]Syncing library: {len(existing_ids)}/{total_items}...[/]")
                page_resp, _ = await self.app.api.get_items(riven_key, limit=limit, page=page)
                if page_resp and "items" in page_resp:
                    for item in page_resp["items"]:
                        p_ids = item.get("parent_ids") or {}
                        # Capture both types of IDs
                        tid = item.get("tmdb_id") or p_ids.get("tmdb_id")
                        tvid = item.get("tvdb_id") or p_ids.get("tvdb_id")
                        if tid: existing_ids.add(str(tid))
                        if tvid: existing_ids.add(str(tvid))

        # 3. Read and filter import file
        status.update("[yellow]Analyzing import file...[/]")
        try:
            with open(file_path, "r") as f:
                import_data = json.load(f)
        except Exception as e:
            status.update(f"[red]Read Error: {e}[/]")
            return

        new_movies = []
        new_shows = []
        skipped_count = 0
        
        for item in import_data:
            item_id = str(item.get("id"))
            if item_id in existing_ids:
                skipped_count += 1
                continue
            
            if item["type"] == "movie":
                new_movies.append(item_id)
            else:
                new_shows.append(item_id)

        total_to_import = len(new_movies) + len(new_shows)
        if total_to_import == 0:
            status.update(f"[green]Import complete: {skipped_count} items skipped (already in library).[/]")
            return

        # 4. Perform Batched Import
        status.update(f"[yellow]Importing {total_to_import} new items (Skipping {skipped_count})...[/]")
        
        batch_size = 50
        imported_count = 0
        error_count = 0

        async def process_batches(items, m_type, id_type):
            nonlocal imported_count, error_count
            for i in range(0, len(items), batch_size):
                batch = items[i:i + batch_size]
                status.update(f"[yellow]Importing {m_type}s: {imported_count}/{total_to_import}...[/]")
                success, msg = await self.app.api.bulk_add_items(m_type, id_type, batch, riven_key)
                if success:
                    imported_count += len(batch)
                else:
                    error_count += len(batch)
                    self.app.log_message(f"Import Error ({m_type}): {msg}")

        if new_movies: await process_batches(new_movies, "movie", "tmdb_ids")
        if new_shows: await process_batches(new_shows, "tv", "tvdb_ids")

        # 5. Final Report
        status.update(
            f"[bold green]Import finished![/]\n"
            f"• [green]Imported:[/] {imported_count}\n"
            f"• [yellow]Skipped:[/] {skipped_count}\n"
            f"• [red]Errors:[/] {error_count}"
        )

    def watch_show_mdblist(self, show: bool) -> None:
        self._update_panel("#mdblist-bulk-area", "#mdblist-header", "MDBList Bulk Manager", show)

    def watch_show_import_export(self, show: bool) -> None:
        self._update_panel("#import-export-area", "#import-export-header", "Import/Export Library", show)

    def _update_panel(self, area_id: str, header_id: str, label: str, show: bool) -> None:
        try:
            self.query_one(area_id).display = show
            header = self.query_one(header_id, Static)
            arrow = "▼" if show else "▶"
            header.update(f"{label} {arrow}")
        except:
            pass

    def on_click(self, event) -> None:
        if event.widget.id == "mdblist-header":
            self.show_mdblist = not self.show_mdblist
        elif event.widget.id == "import-export-header":
            self.show_import_export = not self.show_import_export

    @on(Button.Pressed, "#btn-export-lib")
    async def on_export(self) -> None:
        status = self.query_one("#export-status", Static)
        status.update("[yellow]Initializing export file...[/]")
        
        riven_key = self.app.settings.get("riven_key")
        limit = 500 # Keep URL length and server load safe
        
        # 1. Get total items to establish the range
        resp, err = await self.app.api.get_items(riven_key, limit=1, item_type=["movie", "show"])
        if err or not resp:
            status.update(f"[red]Export Error: {err}[/]")
            return
            
        total = resp.get("total_items", 0)
        if total == 0:
            status.update("[yellow]Library is empty.[/]")
            return
            
        total_pages = (total + limit - 1) // limit
        export_file = "riven_export.json"
        
        # 2. Sequential Batching
        count = 0
        import json
        
        try:
            with open(export_file, "w") as f:
                # Start the JSON array
                f.write("[\n")
                
                for page in range(1, total_pages + 1):
                    status.update(f"[yellow]Processing {count}/{total} (Batch {page}/{total_pages})...[/]")
                    
                    page_resp, page_err = await self.app.api.get_items(riven_key, limit=limit, page=page, item_type=["movie", "show"])
                    
                    if page_resp and "items" in page_resp:
                        items = page_resp["items"]
                        for i, item in enumerate(items):
                            i_type = item.get("type")
                            p_ids = item.get("parent_ids") or {}
                            entry = None
                            
                            if i_type == "movie":
                                val = p_ids.get("tmdb_id")
                                if val: entry = {"type": "movie", "id": str(val)}
                            elif i_type == "show":
                                val = p_ids.get("tvdb_id")
                                if val: entry = {"type": "show", "id": str(val)}
                            
                            if entry:
                                json_str = json.dumps(entry)
                                # Write entry with comma unless it is the very last item of the very last page
                                is_last = (page == total_pages and i == len(items) - 1)
                                f.write(f"    {json_str}{'' if is_last else ','}\n")
                                count += 1
                
                # Close the JSON array
                f.write("]\n")
                
            status.update(f"[green]Export complete! Saved {count} items to {export_file}[/]")
        except Exception as e:
            status.update(f"[red]Write Error: {e}[/]")

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
                # Use the search endpoint for IMDB IDs as proven in your curl
                resp, err = await self.app.api.get_items(riven_key, search=imdb_id, limit=1)
                if resp and resp.get("items"):
                    return resp["items"][0]
            return None

        async def probe_show(s):
            tvdb_id = s.get("tvdb_id")
            if not tvdb_id: return None
            async with semaphore:
                # Use the direct ID lookup endpoint for TVDB as proven in your curl
                item = await self.app.api.get_item_by_id("tv", str(tvdb_id), riven_key)
                return item
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
