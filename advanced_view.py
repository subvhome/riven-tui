from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Static, Label, Button, Input, Log, ListView, ListItem
from textual import on
from typing import List, Dict
import asyncio
from modals import ConfirmationScreen

from textual.reactive import reactive

class AdvancedView(Vertical):
    matched_items: Dict[str, dict] = {} # ID -> Full Item Data
    missing_movies: List[dict] = []
    missing_shows: List[dict] = []
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

                with Horizontal(id="adv-results-row"):
                    with Vertical(classes="advanced-column column-header-root"):
                        yield Label("LIBRARY ITEMS", classes="advanced-sub-label")
                        yield ListView(id="adv-list-root")
                    with Vertical(classes="advanced-column column-header-season"):
                        yield Label("SEASONS", classes="advanced-sub-label")
                        yield ListView(id="adv-list-season")
                    with Vertical(classes="advanced-column column-header-episode"):
                        yield Label("EPISODES", classes="advanced-sub-label")
                        yield ListView(id="adv-list-episode")
                    with Vertical(classes="advanced-column column-header-missing"):
                        yield Label("MISSING (ADD)", classes="advanced-sub-label")
                        yield ListView(id="adv-list-missing")

                with Horizontal(classes="advanced-row", id="adv-actions-row"):
                    yield Button("Mass Add", id="btn-adv-add", variant="success", disabled=True)
                    yield Button("Mass Delete", id="btn-adv-delete", variant="error", disabled=True)
                    yield Button("Mass Reset", id="btn-adv-reset", variant="warning", disabled=True)
                    yield Button("Mass Retry", id="btn-adv-retry", variant="primary", disabled=True)

            # 2. Backup/Restore Section
            yield Static("Backup/Restore Library ▶", id="import-export-header", classes="advanced-header-toggle")
            
            with Vertical(id="import-export-area", classes="bulk-area-panel"):
                with Horizontal(classes="advanced-row"):
                    yield Button("Backup Library", id="btn-export-lib", variant="primary")
                    yield Button("Restore Library", id="btn-import-lib", variant="success")
                
                yield Static("", id="export-status", classes="advanced-status")
                yield Static("") # Blank line spacer
                
                yield Label("Usage Notes:", classes="advanced-sub-label")
                yield Label(
                    "• [bold]Backup[/]: Saves IDs to [cyan]riven_export.json[/]\n"
                    "• [bold]Migration[/]: Move file to new instance folder\n"
                    "• [bold]Restore[/]: Requests all items from file",
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
            "Restore Library",
            f"Are you sure you want to restore items from [cyan]{file_path}[/]?\n\nExisting items will be automatically skipped.",
            confirm_label="Yes, Restore",
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
        self._update_panel("#import-export-area", "#import-export-header", "Backup/Restore Library", show)

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
        
        # Clear all lists
        self.query_one("#adv-list-root", ListView).clear()
        self.query_one("#adv-list-season", ListView).clear()
        self.query_one("#adv-list-episode", ListView).clear()
        self.query_one("#adv-list-missing", ListView).clear()
        self.missing_movies = []
        self.missing_shows = []

        # 1. Fetch Mdblist
        mdb_items, mdb_err = await self.app.api.get_mdblist_items(val)
        if mdb_err:
            status.update(f"[red]Mdblist Error: {mdb_err}[/]")
            return

        all_mdb_movies = mdb_items.get("movies", [])
        all_mdb_shows = mdb_items.get("shows", [])
        
        if not all_mdb_movies and not all_mdb_shows:
            status.update("[yellow]Mdblist is empty or not yet populated.[/]")
            return

        # 2. Surgical Probing
        status.update(f"[yellow]Surgically probing Riven for {len(all_mdb_movies) + len(all_mdb_shows)} items...[/]")
        riven_key = self.app.settings.get("riven_key")
        self.matched_items = {}
        
        semaphore = asyncio.Semaphore(10)

        async def probe_movie(m):
            imdb_id = m.get("imdb_id")
            if not imdb_id: return None
            async with semaphore:
                resp, err = await self.app.api.get_items(riven_key, search=imdb_id, limit=1)
                if resp and resp.get("items"): return resp["items"][0]
            return None

        async def probe_show(s):
            tvdb_id = s.get("tvdb_id")
            if not tvdb_id: return None
            async with semaphore:
                item = await self.app.api.get_item_by_id("tv", str(tvdb_id), riven_key)
                return item
            return None

        # Gather results parallel
        movie_tasks = [probe_movie(m) for m in all_mdb_movies]
        show_tasks = [probe_show(s) for s in all_mdb_shows]
        
        movie_results = await asyncio.gather(*movie_tasks)
        show_results = await asyncio.gather(*show_tasks)

        # 3. Process & Categorize
        counts = {"root": 0, "season": 0, "episode": 0, "missing": 0}
        
        # Helper to process results
        def process_match(item):
            i_id = str(item["id"])
            i_type = item.get("type", "unknown")
            self.matched_items[i_id] = item
            
            target_list_id = None
            if i_type in ["movie", "show"]:
                target_list_id = "#adv-list-root"
                counts["root"] += 1
            elif i_type == "season":
                target_list_id = "#adv-list-season"
                counts["season"] += 1
            elif i_type == "episode":
                target_list_id = "#adv-list-episode"
                counts["episode"] += 1
            
            if target_list_id:
                self.query_one(target_list_id, ListView).append(ListItem(Label(item.get("title", "Unknown"))))

        # Process Movies
        for i, res in enumerate(movie_results):
            if res:
                process_match(res)
            else:
                # Missing
                m_item = all_mdb_movies[i]
                self.missing_movies.append(m_item)
                counts["missing"] += 1
                self.query_one("#adv-list-missing", ListView).append(ListItem(Label(m_item.get("title", "Unknown Movie"))))

        # Process Shows
        for i, res in enumerate(show_results):
            if res:
                process_match(res)
            else:
                # Missing
                s_item = all_mdb_shows[i]
                self.missing_shows.append(s_item)
                counts["missing"] += 1
                self.query_one("#adv-list-missing", ListView).append(ListItem(Label(s_item.get("title", "Unknown Show"))))

        # 4. Final Status
        status.update(f"[green]Scan Complete: Found {counts['root']} Lib Items, {counts['season']} Seasons, {counts['episode']} Episodes. [bold]{counts['missing']} Missing.[/]")
        
        self.query_one("#btn-adv-add", Button).disabled = counts["missing"] == 0
        self.query_one("#btn-adv-delete", Button).disabled = counts["root"] == 0
        self.query_one("#btn-adv-reset", Button).disabled = counts["root"] == 0
        self.query_one("#btn-adv-retry", Button).disabled = counts["root"] == 0

    @on(Button.Pressed, "#btn-adv-add")
    def on_add_click(self) -> None:
        self.run_worker(self.perform_mass_add())

    async def perform_mass_add(self):
        total_missing = len(self.missing_movies) + len(self.missing_shows)
        if total_missing == 0: return

        confirmed = await self.app.push_screen_wait(ConfirmationScreen(
            "Mass Add Items",
            f"Are you sure you want to add [bold]{total_missing}[/] items to your library?\n"
            "This will be done in bursts of 5 items every 2 seconds.",
            confirm_label="Yes, Start Adding",
            variant="success"
        ))
        
        if not confirmed: return

        status = self.query_one("#adv-status-line", Static)
        riven_key = self.app.settings.get("riven_key")
        
        async def process_batch(items, m_type, id_type):
            count = len(items)
            processed = 0
            
            for i in range(0, count, 5):
                batch = items[i:i+5]
                batch_ids = []
                
                # Resolve IDs if needed
                for item in batch:
                    target_id = None
                    if m_type == "movie":
                        target_id = item.get("tmdbid") or item.get("tmdb_id")
                        # Fallback to resolving via IMDB if TMDB is missing
                        if not target_id and item.get("imdb_id"):
                            # This is a bit slow but necessary if MDBList lacks TMDB ID
                            pass # For now assume MDBList provides it or we skip
                    else:
                        target_id = item.get("tvdbid") or item.get("tvdb_id")
                    
                    if target_id:
                        batch_ids.append(str(target_id))
                
                if batch_ids:
                    status.update(f"[green]Mass Add ({m_type.title()}s): Processing {processed + len(batch_ids)}/{count}...[/]")
                    await self.app.api.bulk_add_items(m_type, id_type, batch_ids, riven_key)
                
                processed += len(batch)
                await asyncio.sleep(2) # Burst control

        if self.missing_movies:
            await process_batch(self.missing_movies, "movie", "tmdb_ids")
        
        if self.missing_shows:
            await process_batch(self.missing_shows, "tv", "tvdb_ids")

        status.update("[bold green]Mass Add Complete! Please rescan to verify.[/]")
        self.query_one("#btn-adv-add", Button).disabled = True

    @on(Button.Pressed, "#btn-adv-delete")
    def on_delete_click(self) -> None: self.run_worker(self.run_action("remove", "Delete"))

    @on(Button.Pressed, "#btn-adv-reset")
    def on_reset_click(self) -> None: self.run_worker(self.run_action("reset", "Reset"))

    @on(Button.Pressed, "#btn-adv-retry")
    def on_retry_click(self) -> None: self.run_worker(self.run_action("retry", "Retry"))

    async def run_action(self, action: str, display_name: str):
        if not self.matched_items: return
        
        status = self.query_one("#adv-status-line", Static)
        
        # 1. Separate Actionable from Unsupported
        actionable_ids = []
        unsupported_items = []
        
        for i_id, item in self.matched_items.items():
            if item.get("type") in ["movie", "show"]:
                actionable_ids.append(i_id)
            else:
                unsupported_items.append({"id": i_id, "title": item.get("title", "Unknown"), "type": item.get("type")})

        count = len(actionable_ids)
        if count == 0 and not unsupported_items:
            return

        # 2. Log Unsupported to File
        if unsupported_items:
            import json
            import os
            log_file = "logs/unsupported_bulk.json"
            try:
                with open(log_file, "w") as f:
                    json.dump(unsupported_items, f, indent=4)
                self.app.log_message(f"Advanced: Logged {len(unsupported_items)} unsupported items to {log_file}")
            except Exception as e:
                self.app.log_message(f"Advanced: Failed to write unsupported log: {e}")

        # 3. Confirmation for Actionable
        if count > 0:
            confirmed = await self.app.push_screen_wait(ConfirmationScreen(
                f"Mass {display_name}",
                f"Are you sure you want to {display_name.lower()} [bold]{count}[/] Root items?\n\n"
                f"[yellow]{len(unsupported_items)} Seasons/Episodes will be skipped and logged.[/]",
                confirm_label=f"Yes, {display_name} Roots",
                variant="error" if action == "remove" else "warning"
            ))
            if not confirmed: return
        else:
            self.app.notify(f"No actionable Root items found. {len(unsupported_items)} items skipped.", severity="warning")
            return

        # 4. Batched Execution
        riven_key = self.app.settings.get("riven_key")
        batch_size = 50
        success_count = 0
        fail_count = 0

        for i in range(0, count, batch_size):
            batch = actionable_ids[i:i + batch_size]
            status.update(f"[yellow]{display_name} Progress: {i}/{count}...[/]")
            
            success, msg = await self.app.api.bulk_action(action, batch, riven_key)
            if success:
                success_count += len(batch)
            else:
                fail_count += len(batch)
                error_msg = str(msg)
                for item_id in batch:
                    if item_id in error_msg:
                        title = self.matched_items[item_id].get("title", "Unknown")
                        error_msg = error_msg.replace(item_id, f"{item_id} - {title}")
                self.app.log_message(f"Mass {display_name} Error: {error_msg}")

        # 5. Cleanup
        status.update(f"[bold green]Complete: {success_count} Roots processed. {len(unsupported_items)} Unsupported skipped.[/]")
        # Clear lists
        self.matched_items = {}
        self.query_one("#adv-list-root", ListView).clear()
        self.query_one("#adv-list-season", ListView).clear()
        self.query_one("#adv-list-episode", ListView).clear()
        self.query_one("#btn-adv-delete", Button).disabled = True
        self.query_one("#btn-adv-reset", Button).disabled = True
        self.query_one("#btn-adv-retry", Button).disabled = True
