from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Static, Label, ListView, ListItem, Button, Input, Select, Checkbox
from textual.message import Message
from textual import on
from textual.reactive import reactive
from typing import List, Dict
import calendar
from search import SearchArea
from messages import PageChanged
from search_results import SelectionSquare

class ApplyFilters(Message):
    pass

class FilterPill(Static):
    class Changed(Message):
        def __init__(self, filter_type: str, value: bool) -> None:
            self.filter_type = filter_type
            self.value = value
            super().__init__()

    def __init__(self, label: str, value: bool, filter_type: str):
        super().__init__(label, id=filter_type, classes="filter-pill")
        self.filter_type = filter_type
        self.value = value
        self.add_class(f"pill-{filter_type}")
        if value:
            self.add_class("-on")

    def on_click(self) -> None:
        self.value = not self.value
        self.set_class(self.value, "-on")
        self.post_message(self.Changed(self.filter_type, self.value))

class TypePill(Static):
    def __init__(self, label: str, value: bool, type_id: str):
        super().__init__(label, id=f"lib-filter-type-{type_id}", classes="type-pill")
        self.value = value
        self.type_id = type_id
        if value:
            self.add_class("-active")

    def on_click(self) -> None:
        self.value = not self.value
        self.set_class(self.value, "-active")

class StateListItem(ListItem):
    selected = reactive(False)
    
    class Changed(Message):
        def __init__(self, item: "StateListItem") -> None:
            self.item = item
            super().__init__()

    def __init__(self, label: str, value: str | None, initial_selected: bool = False) -> None:
        super().__init__(classes="state-list-item")
        self.label_text = label
        self.value = value
        self.selected = initial_selected

    def compose(self) -> ComposeResult:
        yield SelectionSquare(self.selected)
        yield Label(self.label_text)

    def watch_selected(self, value: bool) -> None:
        self.set_class(value, "-selected")
        try:
            self.query_one(SelectionSquare).update_value(value)
        except:
            pass

    def on_click(self) -> None:
        self.selected = not self.selected
        self.post_message(self.Changed(self))

class Sidebar(Container):
    @on(StateListItem.Changed)
    def on_state_changed(self, event: StateListItem.Changed):
        items = self.query(StateListItem)
        changed_item = event.item
        
        if changed_item.value is None: # "All" was toggled
            if changed_item.selected:
                # Deselect everything else
                for item in items:
                    if item != changed_item:
                        item.selected = False
        else: # A specific state was toggled
            if changed_item.selected:
                # Deselect "All"
                for item in items:
                    if item.value is None:
                        item.selected = False
        
        # Ensure at least "All" is selected if nothing else is
        if not any(item.selected for item in items):
            for item in items:
                if item.value is None:
                    item.selected = True

    @on(Input.Submitted, "#lib-filter-search")
    def on_search_submitted(self):
        self.post_message(ApplyFilters())

    def compose(self) -> ComposeResult:
        yield SearchArea(id="sidebar-search")
        yield Static("", id="sidebar-title")
        
        # 1. Library Filter Container
        with Vertical(id="sidebar-filters-container", classes="hidden"):
            with Vertical(classes="filter-scroll-area"):
                yield Label("Search:")
                yield Input(placeholder="Search library...", id="lib-filter-search")
                
                yield Label("Type:")
                with Horizontal(id="lib-type-pills"):
                    yield TypePill("Movies", True, "movie")
                    yield TypePill("Shows", True, "show")
                    yield TypePill("Seasons", False, "season")
                    yield TypePill("Episodes", False, "episode")
                    yield TypePill("Anime", False, "anime")
                
                yield Label("States:")
                with ListView(id="lib-filter-states-list"):
                    yield StateListItem("All", None, initial_selected=True)
                    yield StateListItem("Unknown", "Unknown")
                    yield StateListItem("Unreleased", "Unreleased")
                    yield StateListItem("Ongoing", "Ongoing")
                    yield StateListItem("Requested", "Requested")
                    yield StateListItem("Indexed", "Indexed")
                    yield StateListItem("Scraped", "Scraped")
                    yield StateListItem("Downloaded", "Downloaded")
                    yield StateListItem("Symlinked", "Symlinked")
                    yield StateListItem("Completed", "Completed")
                    yield StateListItem("Partially Completed", "PartiallyCompleted")
                    yield StateListItem("Failed", "Failed")
                    yield StateListItem("Paused", "Paused")

                yield Label("Sort:")
                yield Select([
                    ("Date Desc", "date_desc"), 
                    ("Date Asc", "date_asc"), 
                    ("Title Asc", "title_asc"), 
                    ("Title Desc", "title_desc")
                ], prompt="Sort", id="lib-filter-sort", allow_blank=False, value="date_desc")
                
                yield Label("Limit:")
                yield Select([("5", 5), ("10", 10), ("20", 20), ("50", 50)], prompt="Limit", id="lib-filter-limit", allow_blank=False, value=20)

            yield Static("0 of 0 Selected", id="sidebar-total-count")

            with Horizontal(classes="separator-row"):
                yield Button("<<", id="btn-prev-page", classes="blue-separator")
                yield Static("1 of 1", id="sidebar-page-label", classes="red-separator")
                yield Button(" >>", id="btn-next-page", classes="blue-separator")

            with Horizontal(id="sidebar-actions-row"):
                yield Button("Apply\nFilters", id="btn-apply-filters", classes="sidebar-action-btn")
                yield Button("Select\nAll", id="btn-select-all-matches", classes="sidebar-action-btn")
                yield Button("Clear\nSelection", id="btn-clear-selection", classes="sidebar-action-btn")
                yield Button("Advanced\nSettings", id="btn-advanced-toggle", classes="sidebar-action-btn")

            with Vertical(id="sidebar-advanced-container", classes="hidden"):
                with Horizontal(classes="adv-row"):
                    yield Button("Reset", id="btn-adv-reset", classes="adv-box")
                    yield Button("Retry", id="btn-adv-retry", classes="adv-box")
                    yield Button("Remove", id="btn-adv-remove", classes="adv-box")
                with Horizontal(classes="adv-row"):
                    yield Button("Pause", id="btn-adv-pause", classes="adv-box")
                    yield Button("Unpause", id="btn-adv-unpause", classes="adv-box")

        # 3. Calendar Summary Container
        with Vertical(id="sidebar-calendar-container", classes="hidden"):
            yield Static("JUMP TO DATE", classes="sidebar-subtitle")
            with Horizontal(classes="calendar-jumper-row"):
                yield Button("<", id="btn-prev-year-sidebar", classes="jumper-btn")
                yield Label("2026", id="label-year-sidebar", classes="jumper-label")
                yield Button(">", id="btn-next-year-sidebar", classes="jumper-btn")
            
            with Horizontal(classes="calendar-jumper-row"):
                yield Button("<", id="btn-prev-month-sidebar", classes="jumper-btn")
                yield Label("January", id="label-month-sidebar", classes="jumper-label")
                yield Button(">", id="btn-next-month-sidebar", classes="jumper-btn")
            
            yield Static("_" * 38, classes="sidebar-separator")
            with Vertical(id="calendar-grid-container"):
                pass

    def on_mount(self) -> None:
        self.show_blank()

    async def update_calendar_grid(self, year: int, month: int, active_days: set) -> None:
        self.query_one("#label-year-sidebar", Label).update(str(year))
        self.query_one("#label-month-sidebar", Label).update(calendar.month_name[month])
        
        container = self.query_one("#calendar-grid-container")
        await container.query("*").remove()
        
        # Header - Dynamic based on locale
        first_day = calendar.firstweekday()
        days = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
        # Reorder days based on first_day index
        ordered_days = days[first_day:] + days[:first_day]
        
        header_labels = [Label(day, classes="grid-cell grid-header-cell") for day in ordered_days]
        await container.mount(Horizontal(*header_labels, classes="calendar-grid-row"))
        
        # Weeks - Dynamic based on locale
        cal_obj = calendar.Calendar(firstweekday=first_day)
        cal = cal_obj.monthdayscalendar(year, month)
        for week in cal:
            week_widgets = []
            for day in week:
                if day == 0:
                    week_widgets.append(Label(" ", classes="grid-cell"))
                else:
                    classes = "grid-cell day-cell"
                    if day in active_days:
                        classes += " has-content"
                    week_widgets.append(Button(str(day), id=f"btn-cal-day-{day}", classes=classes))
            await container.mount(Horizontal(*week_widgets, classes="calendar-grid-row"))

    def update_pagination(self, page: int, total_pages: int, total_items: int = 0, selected_count: int = 0) -> None:
        try:
            prev_btn = self.query_one("#btn-prev-page", Button)
            prev_btn.disabled = page <= 1
        except Exception:
            pass

        try:
            next_btn = self.query_one("#btn-next-page", Button)
            next_btn.disabled = page >= total_pages
        except Exception:
            pass

        try:
            self.query_one("#sidebar-page-label", Static).update(f"[bold]{page}[/] of [bold]{total_pages}[/]")
        except Exception:
            pass
            
        self.update_selection_count(selected_count, total_items)

    def update_selection_count(self, selected: int, total: int = 0) -> None:
        try:
            label = self.query_one("#sidebar-total-count", Static)
            label.update(f"[bold #FFFFFF]{selected}[/] of {total} Selected")
        except Exception:
            pass

    def _hide_all(self) -> None:
        self.query_one("#sidebar-title", Static).update("")
        self.query_one("#sidebar-search").add_class("hidden")
        self.query_one("#sidebar-filters-container").add_class("hidden")
        self.query_one("#sidebar-calendar-container").add_class("hidden")

    def show_blank(self) -> None:
        self._hide_all()

    def show_library_filters(self) -> None:
        self._hide_all()
        self.query_one("#sidebar-title", Static).update("LIBRARY FILTERS")
        self.query_one("#sidebar-filters-container").remove_class("hidden")

    def show_calendar_summary(self) -> None:
        self._hide_all()
        self.query_one("#sidebar-title", Static).update("CALENDAR")
        self.query_one("#sidebar-calendar-container").remove_class("hidden")

    def get_filter_values(self) -> dict:
        selected_types = []
        for t in ["movie", "show", "season", "episode", "anime"]:
            if self.query_one(f"#lib-filter-type-{t}", TypePill).value:
                selected_types.append(t)

        selected_states = [
            item.value for item in self.query(StateListItem) 
            if item.selected and item.value is not None
        ]
        
        # If no specific states selected, or "All" is selected, pass None
        final_states = selected_states if selected_states else None

        return {
            "search": self.query_one("#lib-filter-search", Input).value,
            "type": selected_types if selected_types else ["movie", "show"], # Default if none selected
            "states": final_states,
            "sort": self.query_one("#lib-filter-sort", Select).value,
            "limit": self.query_one("#lib-filter-limit", Select).value,
        }

    def toggle_advanced(self) -> None:
        container = self.query_one("#sidebar-advanced-container")
        container.set_class(not container.has_class("hidden"), "hidden")
