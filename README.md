# Riven TUI

A terminal-based management interface for [Riven](https://github.com/rivenmedia/riven). 

Built for those who prefer staying in the shell, this TUI provides a visual way to monitor your library, search for content, and maintain your collection without opening a browser.

![Riven TUI](assets/riven-tui.gif)

## Key Features

- **Central Dashboard**: Real-time library statistics, service health status, recently added media, and trending content with a **quick request button** `[+]` for instant additions.
- **Library Management**: Browse your collection with deep filtering (Type, State, Sort). Includes a compact **Action Bar** for rapid navigation and filter application.
- **Bulk Operations**: Multi-select items directly in the library view to perform batch **Reset**, **Retry**, **Remove**, **Pause**, or **Unpause** tasks with integrated safety confirmation modals.
- ~~**Manual Scraping**: A full workflow for stream discovery, torrent selection, and file-to-episode mapping directly from the TUI.~~ *(Temporarily disabled)*
- **Live Logs**: Dedicated full-screen log viewer with real-time updates, keyword filtering, and negation support.
- **Settings Editor**: Complete tree-based configuration editor for all Riven backend settings.
- **Advanced Suite**: Mass-action maintenance tools and external list scanning (e.g., [Mdblist](https://mdblist.com/)).
- **Posters & Visuals**: High-resolution poster rendering using [chafa](https://hpjansson.org/chafa/).
- **Debug Window**: Toggleable real-time technical log overlay (`Ctrl+T`) with automated redaction of sensitive API keys. *(Active-only capture)*

## Installation

```bash
curl -sSL https://raw.githubusercontent.com/subvhome/riven-tui/main/install.sh | bash
```

### Manual Setup
1. `git clone https://github.com/subvhome/riven-tui.git`
2. `pip install -r requirements.txt`
3. `cp settings.json.example settings.json`
4. `python riven_tui.py`

## Screenshots

| Dashboard | Library |
| :---: | :---: |
| ![Dashboard](assets/welcome-dashboard.jpg) | ![Library](assets/library.jpg) |

| Search | Media Detail |
| :---: | :---: |
| ![Search](assets/search.jpg) | ![Media Card](assets/search-mediacard.jpg) |

| Calendar | Advanced |
| :---: | :---: |
| ![Calendar](assets/calendar.jpg) | ![Advanced](assets/advanced.jpg) |

| Logs | Debug Window |
| :---: | :---: |
| ![Logs](assets/logs.jpg) | ![Debug Window](assets/debug-window.jpg) |

## ⚙️ Core Functionality

### Selection & Batch Tasks
Located within the Library Sidebar's "Advanced Settings" toggle. 
- **Multi-Select**: Use the mouse to select items across pages.
- **Safety First**: Confirmation modals list all selected titles before any API calls are executed.
- **Batch Actions**: Instantly trigger Reset, Retry, Remove, Pause, or Unpause for your entire selection.

### Mass Manager (External Lists)
The Advanced tab allows you to cross-reference your Riven library with external lists to find matches and perform bulk maintenance.

### Enriched Search
Search results are automatically cross-referenced with your Riven library. Existing items are badged with their current state (**Completed**, **Indexed**, **Scraped**, etc.) and color-coded for instant recognition.

## Configuration

Settings are managed in `settings.json` or via the in-app editor:

- `riven_key`: Your Riven API key.
- `tmdb_bearer_token`: [TMDB Read Access Token](https://www.themoviedb.org/settings/api).
- `be_config`: Connection details for your Riven backend.
- `chafa_max_width`: Maximum width for poster rendering.
- `log_display_limit`: Lines to fetch on initial log load.

---
Built with [Textual](https://github.com/Textualize/textual).