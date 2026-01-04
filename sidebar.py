from textual.widgets import Static, ListView, ListItem, Label, Button
from textual.containers import Container
from textual.app import ComposeResult

class Sidebar(Container):
    def compose(self) -> ComposeResult:
        yield Static("CATEGORIES", id="sidebar-title")
        yield ListView(id="sidebar-list")
        yield Button("Back to Categories", id="sidebar-footer-link", variant="primary") 

    def on_mount(self) -> None:
        self.show_categories()

    def show_categories(self) -> None:
        self.query_one("#sidebar-title", Static).update("CATEGORIES")
        self.query_one("#sidebar-footer-link").display = False
        
        categories = ["Movies", "TV Shows", "Downloads", "Settings"]
        items = [ListItem(Label(cat)) for cat in categories]
        # We don't attach item_data here so they don't trigger JSON display
        
        lv = self.query_one(ListView)
        lv.clear()
        lv.extend(items)

    def update_results(self, query: str, results: list) -> None:
        """Updates the sidebar with formatted search results."""
        self.query_one("#sidebar-title", Static).update(f"Results: {query}")
        self.query_one("#sidebar-footer-link").display = True
        
        lv = self.query_one(ListView)
        lv.clear()
        
        if not results:
            lv.extend([ListItem(Label("No Results Found"))])
        else:
            for item in results:
                m_type = item.get('media_type', 'unknown')
                title = item.get('title', 'Unknown')
                # Format: ({media_type}){title}
                li = ListItem(Label(f"({m_type}){title}"))
                li.item_data = item # Store raw JSON for the MainContent area
                lv.extend([li])