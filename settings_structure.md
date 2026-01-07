# Riven TUI Settings Structure Markup

## [Node] General
*Root keys with no nesting*
- version (String)
- api_key (String)
- log_level (Select: DEBUG, INFO, WARNING, ERROR)
- enable_network_tracing (Boolean)
- enable_stream_tracing (Boolean)
- retry_interval (Integer)
- tracemalloc (Boolean)

## [Node] Filesystem
- mount_path (String)
- cache_dir (String)
- cache_max_size_mb (Integer)
- cache_ttl_seconds (Integer)
- cache_eviction (String)
- cache_metrics (Boolean)

### [Sub-Node] Library Profiles
*Iterate through 'library_profiles' dict*
- [Profile Name]
    - enabled (Boolean)
    - library_path (String)
    - filter_rules (Complex/Nested)

### [Sub-Node] Naming Templates
- movie_dir_template (String)
- movie_file_template (String)
- show_dir_template (String)
- season_dir_template (String)
- episode_file_template (String)

## [Node] Updaters
- updater_interval (Integer)
- library_path (String)

### [Sub-Node] Media Servers
- Plex (enabled, token, url)
- Jellyfin (enabled, api_key, url)
- Emby (enabled, api_key, url)

## [Node] Downloaders
- video_extensions (List/CSV)
- movie_filesize_mb_min (Integer)
- movie_filesize_mb_max (Integer)
- episode_filesize_mb_min (Integer)
- episode_filesize_mb_max (Integer)
- proxy_url (String)

### [Sub-Node] Debrid Services
- Real-Debrid (enabled, api_key)
- Debrid-Link (enabled, api_key)
- AllDebrid (enabled, api_key)

## [Node] Content
### [Sub-Node] Services
- Overseerr (enabled, url, api_key, update_interval, use_webhook)
- Plex Watchlist (enabled, update_interval, rss list)
- MDBList (enabled, api_key, update_interval, lists)
- Listrr (enabled, api_key, update_interval, movie_lists, show_lists)
- Trakt (enabled, api_key, update_interval, watchlist, user_lists, collection, etc.)
