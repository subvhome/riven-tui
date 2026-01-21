from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Static, Label, ListView, ListItem, Button, Input, Select, Checkbox
from textual.message import Message
from textual import on
from typing import List, Dict
import calendar
from search_results import SearchResultItem
from search import SearchArea
from messages import PageChanged

class PaginationControl(Horizontal):
    def __init__(self, page: int, total_pages: int) -> None:
        super().__init__(id="pagination-container")
        self.page = page
        self.total_pages = total_pages

    def compose(self) -> ComposeResult:
        yield Button("<", id="btn-prev-page", disabled=self.page <= 1)
        yield Label(f"Page {self.page} of {self.total_pages}", classes="pagination-label")
        yield Button(">", id="btn-next-page", disabled=self.page >= self.total_pages)

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

class Sidebar(Container):
    def compose(self) -> ComposeResult:
        yield SearchArea(id="sidebar-search")
        yield Static("", id="sidebar-title")
        
        # 1. Main List Container (for Search Results, etc)
        with Vertical(id="sidebar-list-container", classes="hidden"):
            yield ListView(id="sidebar-list")
        
        # 2. Library Filter Container
        with Vertical(id="sidebar-filters-container", classes="hidden"):
            with Vertical(classes="filter-scroll-area"):
                yield Label("Search:")
                yield Input(placeholder="Search library...", id="lib-filter-search")
                
                yield Label("Type:")
                yield Select([
                    ("All", None), 
                    ("Movie", "movie"), 
                    ("TV Show", "show"),
                    ("Anime", "anime")
                ], prompt="Type", id="lib-filter-type", allow_blank=False, value=None)
                
                yield Label("States:")
                yield Select([
                    ("All", None),
                    ("Unknown", "Unknown"),
                    ("Unreleased", "Unreleased"),
                    ("Ongoing", "Ongoing"),
                    ("Requested", "Requested"),
                    ("Indexed", "Indexed"),
                    ("Scraped", "Scraped"),
                    ("Downloaded", "Downloaded"),
                    ("Symlinked", "Symlinked"),
                    ("Completed", "Completed"),
                    ("Partially Completed", "PartiallyCompleted"),
                    ("Failed", "Failed"),
                    ("Paused", "Paused")
                ], prompt="States", id="lib-filter-states", allow_blank=False, value=None)

                yield Label("Sort:")
                yield Select([
                    ("Date Desc", "date_desc"), 
                    ("Date Asc", "date_asc"), 
                    ("Title Asc", "title_asc"), 
                    ("Title Desc", "title_desc")
                ], prompt="Sort", id="lib-filter-sort", allow_blank=False, value="date_desc")
                
                yield Label("Limit:")
                yield Select([("5", 5), ("10", 10), ("20", 20), ("50", 50)], prompt="Limit", id="lib-filter-limit", allow_blank=False, value=20)
                
                yield Label("Page:")
                yield Input("1", placeholder="Page", id="lib-filter-page")

            yield Button("Apply Filters", id="btn-apply-filters", variant="success")
            yield Vertical(id="sidebar-lib-pagination")

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

    def _hide_all(self) -> None:
        self.query_one("#sidebar-title", Static).update("")
        self.query_one("#sidebar-search").add_class("hidden")
        self.query_one("#sidebar-list-container").add_class("hidden")
        self.query_one("#sidebar-filters-container").add_class("hidden")
        self.query_one("#sidebar-calendar-container").add_class("hidden")

    def show_blank(self) -> None:
        self._hide_all()

    def show_search(self) -> None:
        self._hide_all()
        self.query_one("#sidebar-search").remove_class("hidden")
        self.query_one("#sidebar-search #search-input").focus()

    def show_library_filters(self) -> None:
        self._hide_all()
        self.query_one("#sidebar-title", Static).update("LIBRARY FILTERS")
        self.query_one("#sidebar-filters-container").remove_class("hidden")

    def show_calendar_summary(self) -> None:
        self._hide_all()
        self.query_one("#sidebar-title", Static).update("CALENDAR")
        self.query_one("#sidebar-calendar-container").remove_class("hidden")

    def update_results(self, query: str, results: list) -> None:
        self._hide_all()
        self.query_one("#sidebar-title", Static).update(f"Results: {query}")
        self.query_one("#sidebar-list-container").remove_class("hidden")
        
        lv = self.query_one("#sidebar-list", ListView)
        lv.clear()
        
        if not results:
            lv.extend([ListItem(Label("No Results Found"))])
        else:
            for item in results:
                lv.append(SearchResultItem(item))

    def get_filter_values(self) -> dict:
        return {
            "search": self.query_one("#lib-filter-search", Input).value,
            "type": self.query_one("#lib-filter-type", Select).value,
            "states": self.query_one("#lib-filter-states", Select).value,
            "sort": self.query_one("#lib-filter-sort", Select).value,
            "limit": self.query_one("#lib-filter-limit", Select).value,
            "page": self.query_one("#lib-filter-page", Input).value,
        }