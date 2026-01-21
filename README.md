# Riven TUI

A terminal-based management interface for [Riven](https://github.com/rivenmedia/riven). 

Built for those who prefer staying in the shell, this TUI provides a visual way to monitor your library, search for content, and handle manual scrapes without opening a browser.

![Dashboard](assets/welcome-dashboard.jpg)

## What's inside

- **Central Dashboard**: A single view for library statistics, service health status, recently added media, and trending content.
- **Library Management**: Browse your collection with powerful filters (Type, State, Sort). View detailed metadata and manage items (Delete, Reset, Retry).
- **Manual Scraping**: A full workflow for stream discovery, torrent selection, and file-to-episode mapping directly from the TUI.
- **Live Logs**: A dedicated, full-screen log viewer with real-time updates, keyword filtering, and negation support.
- **Debug Window**: A toggleable real-time technical log overlay (`Ctrl+T`) with automated redaction of sensitive API keys and tokens.
- **Settings Editor**: A complete, tree-based configuration editor for your Riven backend settings.
- **Advanced Management**: Mass-action suite for library maintenance. Scan external lists (like [Mdblist](https://mdblist.com/)) and bulk Delete, Reset, or Retry items in your library.
- **Posters & Visuals**: High-resolution poster rendering using [chafa](https://hpjansson.org/chafa/) with optimized aspect ratios for standard media posters.

## Installation

The easiest way to get set up is the interactive install script. It handles the virtual environment, dependencies, and guides you through the initial configuration.

```bash
curl -sSL https://raw.githubusercontent.com/subvhome/riven-tui/main/install.sh | bash
```

## Running the application

If you used the **Quick Install** script above, you can start the TUI in two ways:

1.  **Directly**: Navigate to your installation folder and run the provided script:
    ```bash
    ./run.sh
    ```
2.  **Via Alias**: If you opted to add an alias during installation, simply type:
    ```bash
    riven-tui
    ```

### Manual Setup
1. Clone the repo: `git clone https://github.com/subvhome/riven-tui.git`
2. Create a venv and install requirements: `pip install -r requirements.txt`
3. Initialize settings: `cp settings.json.example settings.json`
4. Run: `python riven_tui.py`

## Screenshots

| Library | Search |
| :---: | :---: |
| ![Library](assets/library.jpg) | ![Search](assets/search.jpg) |

| Media Detail | Calendar |
| :---: | :---: |
| ![Media Card](assets/search-mediacard.jpg) | ![Calendar](assets/calendar.jpg) |

## ⚙️ Advanced Features

### Mass List Management
The Advanced tab allows you to cross-reference your Riven library with external lists (e.g., [Mdblist](https://mdblist.com/)).
- **Scan**: Paste a list ID or URL to find matching items in your library.
- **Mass Action**: Delete, Reset, or Retry all matched items in a single batch.

### Enriched Search & States
Search results are automatically cross-referenced with your Riven library. Items already in your collection are badged with their current state (**Completed**, **Indexed**, **Scraped**, etc.) and color-coded for instant recognition.

### Localized Calendar
The calendar view automatically detects your system locale to set the first day of the week (e.g., Sunday for USA, Monday for France). TV events are formatted clearly with show titles and season/episode numbering.

## Configuration

Settings are managed in `settings.json`. The installer will prompt you for these, but you can edit them manually at any time:

- `riven_key`: Your Riven API key.
- `tmdb_bearer_token`: [TMDB Read Access Token](https://www.themoviedb.org/settings/api) for search and discovery.
- `be_config`: Connection details for your Riven backend.
- `chafa_max_width`: Maximum width for poster rendering (default: 100).
- `log_level`: Verbosity of logs (`DEBUG`, `INFO`, `WARNING`, `ERROR`).
- `log_display_limit`: Number of lines to fetch on initial log load.
- `log_refresh_interval`: Seconds between auto-refreshes in the log view.

## Controls

The UI supports both keyboard and mouse.
- **Tab**: Cycle focus between widgets.
- **Arrows**: Navigate lists and grids.
- **Enter**: Select items.
- **Ctrl + T**: Toggle the secure Debug Log overlay.

---
Built with [Textual](https://github.com/Textualize/textual).