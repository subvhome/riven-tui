# Riven TUI

A high-performance terminal-based alternative to the Riven Web interface. 

Riven TUI turns your shell into a dedicated media kiosk, allowing you to discover, request, and maintain your entire collection with the speed and efficiency of a native terminal application.

<p align="center">
  <img src="assets/riven-tui.gif" width="85%" />
</p>

## Key Features

- **Complete Web UI Replacement**: Manage your full Riven lifecycle entirely from the terminal.
- **Frictionless Media Requesting**: Streamlined "Media Wall" powered by TMDB with quick-add functionality.
- **Real-Time Library Governance**: Deep cross-referencing between TMDB and Riven with badged pipeline states.
- **Advanced Bulk Management**: Comprehensive MDBList support for mass additions and maintenance.
- **Background Event Tracking**: Global log collection ensures you never miss a background task status.
- **Dynamic Theming**: Instant theme switching with support for custom TCSS palettes.
- **Maintenance Power Tools**: Selective batch processing and automated backup/restore suites.
- **Native Visual Experience**: High-resolution poster rendering directly in your shell via `chafa`.

## Installation

### Standard Linux (Debian, Ubuntu, Fedora, Arch, macOS)
Supports most distributions using `apt`, `dnf`, `pacman`, or `brew`.
```bash
curl -sSL https://raw.githubusercontent.com/subvhome/riven-tui/main/install.sh | bash
```

### Alpine Linux
Pure POSIX-compliant installer optimized for Alpine's `apk` and `ash` shell.
```bash
wget -qO- https://raw.githubusercontent.com/subvhome/riven-tui/main/install_alpine.sh | sh
```

### Manual Setup
1. Install **chafa** (system package) for image support.
2. `git clone https://github.com/subvhome/riven-tui.git`
3. `pip install -r requirements.txt`
4. `cp settings.json.example settings.json`
5. `python riven_tui.py`

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

### MDBList Mass Manager
Located in the Advanced tab. A powerful bulk tool for MDBList users:
- **Surgical Probe**: Scans a list and categorizes results into **Library Items**, **Seasons**, **Episodes**, and **Missing**.
- **Mass Add**: Queue and add hundreds of missing items in safe, throttled bursts (5 items every 2 seconds) to avoid backend flooding.
- **Mass Cleanup**: Perform batch **Reset, Retry, or Delete** operations on matched items.

### Batch Tasks & Selection
Power tools for collection cleanup. Select multiple items across your library view (using the mouse or Space) to trigger mass actions with integrated safety confirmations that list all affected titles.

### Backup & Restore
Safely migrate or archive your library. **Backup** streams your library IDs to a JSON file in safe batches, while **Restore** performs a pre-import sync to skip duplicates and avoid backend errors.

### Global Background Logs
A system-wide log collector that runs in the background. Toggle it with **`Ctrl+L`** to capture events while you work in other tabs. A visual status indicator in the header keeps you informed of background activity.

### Instant Theme Cycling
Personalize your cockpit instantly by pressing **`Ctrl+Y`**. The TUI scans the `themes/` directory and applies new color palettes on the fly, saving your preference automatically.

## Configuration

Settings are managed in `settings.json` or via the in-app **Settings Tree**:

- `riven_key`: Your Riven API key.
- `tmdb_bearer_token`: TMDB Read Access Token.
- `theme`: The name of the active theme (e.g., `dracula`, `nord`, `default`).
- `chafa_max_width`: Maximum width for rendered media posters.

---
Built with [Textual](https://github.com/Textualize/textual).