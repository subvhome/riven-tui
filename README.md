# Riven TUI

A high-performance terminal-based alternative to the Riven Web interface. 

Riven TUI turns your shell into a dedicated media kiosk, allowing you to discover, request, and maintain your entire collection with the speed and efficiency of a native terminal application.

<p align="center">
  <img src="assets/riven-tui.gif" width="85%" />
</p>

## Key Features

- **Complete Web UI Replacement**: Manage your Riven lifecycle entirely from the terminal. Monitor server health, library statistics, and collection distribution at a glance.
- **Frictionless Media Requesting**: A streamlined "Media Wall" powered by TMDB. Use the quick-add `[+]` button on trending items or deeper metadata cards to get content into your system instantly.
- **Real-Time Library Governance**: Deep cross-referencing between TMDB and your Riven backend. Items are badged by their current pipeline state (e.g., *Completed, Scraped*). Features a new **Backup & Restore** suite for easy library migration.
- **Dynamic Theme System**: Personalize your cockpit with built-in themes like **Dracula**, **Nord**, and **Gruvbox**. Cycle through them instantly with `Ctrl+Y`.
- **Structural Matcher (Advanced View)**: A 3-column diagnostic tool that categorizes MDBList matches into **Root**, **Season**, and **Episode** buckets, ensuring only actionable items are processed in bulk.
- **Integrated Maintenance Suite**: Power tools for collection cleanup. Multi-select items across your library to perform batch **Reset, Retry, Remove, Pause,** or **Unpause** tasks with safety confirmations.
- **Transparent Troubleshooting**: A dedicated full-screen log viewer with real-time updates and a secure, redacted debug overlay (`Ctrl+T`). *Note: Existence probes are now silent and no longer flood backend logs with 404 errors.*
- ~~**Manual Scrape Workflow**: Surgical stream discovery and file-to-episode mapping directly within the TUI.~~ *(Temporarily disabled)*
- **Native Visual Experience**: High-resolution poster rendering using `chafa`.

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

### Instant Theme Cycling
Switch themes on the fly by pressing **`Ctrl+Y`**. The TUI scans the `themes/` directory and applies new color palettes immediately, saving your preference to your settings.

### Backup & Restore
Located in the Advanced tab. **Backup** streams your library IDs to a JSON file in safe batches, while **Restore** performs a pre-import sync to skip duplicates and avoid backend errors.

### Batch Tasks & Selection
Select multiple items in the library view (using the mouse or Space) to trigger mass actions with integrated safety confirmations that list all affected titles.

## Configuration

Settings are managed in `settings.json` or via the in-app **Settings Tree**:

- `riven_key`: Your Riven API key.
- `tmdb_bearer_token`: TMDB Read Access Token.
- `theme`: The name of the active theme (e.g., `dracula`, `nord`, `default`).
- `chafa_max_width`: Maximum width for rendered media posters.

---
Built with [Textual](https://github.com/Textualize/textual).