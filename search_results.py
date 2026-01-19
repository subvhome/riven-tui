from textual.app import ComposeResult
from textual.widgets import ListItem, Label
from rich.text import Text

class SearchResultItem(ListItem):
    def __init__(self, item_data: dict) -> None:
        super().__init__(classes="sidebar-item-layout")
        self.item_data = item_data
        
        # Line 1: Title and Year
        title_text = item_data.get('title') or item_data.get('name') or 'Unknown'
        release_date = item_data.get('release_date') or item_data.get('first_air_date')
        self.year = f" [{release_date[:4]}]" if release_date and len(release_date) >= 4 else ""
        self.title = title_text
        self.tagline = item_data.get('tagline', '')

    def compose(self) -> ComposeResult:
        yield Label(Text.assemble((self.title, "bold"), (self.year, "dim")), classes="search-item-title")
        yield Label(f'"{self.tagline}"' if self.tagline else "", classes="search-item-tagline")
        
        # Line 3: Rating and Genres
        raw_rating = self.item_data.get('vote_average') or self.item_data.get('rating') or 0
        rating = float(raw_rating)
        star = "⭐" if rating > 0 else ""
        rating_text = f"{star}{rating:.1f}" if rating > 0 else "No Rating"
        
        genres_list = self.item_data.get('genres', [])
        if genres_list:
            genre_names = [g.get('name') for g in genres_list[:2]]
            genres_text = ", ".join(genre_names)
        else:
            genres_text = "Unknown"
            
        yield Label(f"{rating_text} - {genres_text}", classes="search-item-meta")
        yield Label("") # Blank line for spacing

class LibraryItemCard(ListItem):
    def __init__(self, item_data: dict) -> None:
        super().__init__(classes="sidebar-item-layout library-item-card")
        self.item_data = item_data
        
        # Line 1: Title and Year
        title_text = item_data.get('title') or 'Unknown'
        aired_at = item_data.get('aired_at')
        self.year = f" [{aired_at[:4]}]" if aired_at and len(aired_at) >= 4 else ""
        self.title = title_text
        self.tagline = item_data.get('tagline', '')

    def compose(self) -> ComposeResult:
        yield Label(Text.assemble((self.title, "bold"), (self.year, "dim")), classes="search-item-title")
        yield Label(f'"{self.tagline}"' if self.tagline else "", classes="search-item-tagline")
        
        # Line 3: Meta (Rating - Genres - State - Content Rating)
        raw_rating = self.item_data.get('vote_average') or self.item_data.get('rating') or 0
        rating_val = float(raw_rating)
        star = "⭐" if rating_val > 0 else ""
        rating_text = f"{star}{rating_val:.1f}" if rating_val > 0 else "No Rating"
        
        genre_ids = self.item_data.get('genre_ids', [])
        genre_names = [self.app.tmdb_genres.get(gid) for gid in genre_ids if self.app.tmdb_genres.get(gid)]
        genres_text = ", ".join(genre_names) if genre_names else ""
        
        state = self.item_data.get('state', 'Unknown')
        content_rating = self.item_data.get('content_rating') or 'N/A'
        
        meta_parts = [rating_text]
        if genres_text: meta_parts.append(genres_text)
        meta_parts.extend([state, content_rating])
        
        yield Label(" - ".join(meta_parts), classes="search-item-meta")
        yield Label("") # Blank line for spacing