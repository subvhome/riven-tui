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
        
        # 1. Gather essential keys
        raw_title = item_data.get('title') or item_data.get('name') or 'Unknown'
        parent_title = item_data.get('parent_title') or item_data.get('show_title') or item_data.get('showName')
        aired_at = item_data.get('aired_at')
        self.year = f" [{aired_at[:4]}]" if aired_at and len(aired_at) >= 4 else ""
        self.item_type = item_data.get('type', 'movie')
        
        # Support both snake_case and camelCase for numbers, prioritising Riven's exact keys
        self.s_num = item_data.get('season_number')
        if self.s_num is None: self.s_num = item_data.get('seasonNumber')
        if self.s_num is None: self.s_num = item_data.get('season')
        
        self.e_num = item_data.get('episode_number')
        if self.e_num is None: self.e_num = item_data.get('episodeNumber')
        if self.e_num is None: self.e_num = item_data.get('episode')

        # 2. Specific Title Logic
        if self.item_type == 'show':
            self.title = raw_title
        elif self.item_type == 'season' and parent_title:
            self.title = f"{parent_title} - Season {self.s_num}" if self.s_num is not None else f"{parent_title} - {raw_title}"
        elif self.item_type == 'episode' and parent_title:
            self.title = f"{parent_title} - {raw_title}"
        else:
            self.title = raw_title

        self.tagline = item_data.get('tagline', '')

    def compose(self) -> ComposeResult:
        # 3. Specific Tagline Logic
        display_tagline = self.tagline
        
        def to_int(val):
            try: return int(val)
            except: return None

        s_int = to_int(self.s_num)
        e_int = to_int(self.e_num)

        if self.item_type == 'episode':
            if s_int is not None and e_int is not None:
                code = f"S{s_int:02d}E{e_int:02d}"
                display_tagline = f"{code} • {self.tagline}" if self.tagline else code
            elif s_int is not None:
                display_tagline = f"Season {s_int} • {self.tagline}" if self.tagline else f"Season {s_int}"
        elif self.item_type == 'season':
            if s_int is not None:
                # If tagline is just the season name again, skip it
                if not self.tagline or self.tagline.lower() == f"season {s_int}":
                    display_tagline = f"Season {s_int}"
                else:
                    display_tagline = f"Season {s_int} • {self.tagline}"

        yield Label(Text.assemble((self.title, "bold"), (self.year, "dim")), classes="search-item-title")
        yield Label(f'"{display_tagline}"' if display_tagline else "", classes="search-item-tagline")

        # Line 3: Meta (Rating - Genres - State - Content Rating)
        raw_rating = self.item_data.get('vote_average') or self.item_data.get('rating') or 0
        rating_val = float(raw_rating)
        star = "⭐" if rating_val > 0 else ""
        rating_text = f"{star}{rating_val:.1f}" if rating_val > 0 else "No Rating"
        
        genre_ids = self.item_data.get('genre_ids', [])
        genre_names = []
        if hasattr(self.app, "tmdb_genres"):
            genre_names = [self.app.tmdb_genres.get(gid) for gid in genre_ids if self.app.tmdb_genres.get(gid)]
        
        # Fallback to local genres if TMDB enrichment isn't available
        if not genre_names and self.item_data.get('genres'):
            for g in self.item_data['genres']:
                if isinstance(g, str):
                    genre_names.append(g.capitalize())
                elif isinstance(g, dict) and g.get('name'):
                    genre_names.append(g['name'].capitalize())
            
        genres_text = ", ".join(genre_names) if genre_names else ""
        
        state = self.item_data.get('state', 'Unknown').title()
        content_rating = self.item_data.get('content_rating') or 'N/A'
        
        meta_parts = [rating_text]
        if genres_text: meta_parts.append(genres_text)
        
        # Add Anime badge if applicable
        if self.item_data.get('is_anime'):
            meta_parts.append("[bold magenta]Anime[/]")
            
        meta_parts.extend([state, content_rating])
        
        yield Label(" • ".join(meta_parts), classes="search-item-meta")
        yield Label("") # Blank line for spacing