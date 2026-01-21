import httpx
import asyncio
import logging
from typing import List, Optional

class RivenAPI:
    def __init__(self, be_base_url, timeout=10.0):
        self.mdblist_api_key = "kgx75hvk95is39a6joe68tgux"
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Referer": f"{be_base_url}/scalar"
        }
        self.client = httpx.AsyncClient(follow_redirects=True, timeout=timeout, headers=headers)
        self.be_base_url = be_base_url
        self.tmdb_base_url = "https://api.themoviedb.org/3"
        self.mdblist_base_url = "https://api.mdblist.com"
        self.logger = logging.getLogger("Riven.API")
        self.logger.propagate = True

    async def get_mdblist_items(self, list_url_or_id: str):
        # Handle full URL or just the "user/listname" string
        path = list_url_or_id.replace("https://mdblist.com/lists/", "").replace("https://api.mdblist.com/lists/", "")
        
        # Ensure path is clean and ends with /items/
        path = path.strip("/")
        url = f"{self.mdblist_base_url}/lists/{path}/items/"
        params = {"apikey": self.mdblist_api_key}
        
        self.logger.debug(f"get_mdblist_items: URL={url}")
        
        try:
            resp = await self.client.get(url, params=params)
            if resp.status_code == 200:
                return resp.json(), None
            return None, f"Mdblist error: {resp.status_code} - {resp.text}"
        except Exception as e:
            self.logger.error(f"get_mdblist_items exception: {e}", exc_info=True)
            return None, str(e)

    async def get_mdblist_item_by_external_id(self, source: str, external_id: str):
        # source: tvdb or tmdb
        url = f"{self.mdblist_base_url}/{source}/{external_id}"
        if source == "tmdb":
             url = f"{self.mdblist_base_url}/tmdb/movie/{external_id}"

        params = {"apikey": self.mdblist_api_key}
        self.logger.debug(f"get_mdblist_item: URL={url}")
        
        try:
            resp = await self.client.get(url, params=params)
            if resp.status_code == 200:
                return resp.json(), None
            return None, f"Mdblist error: {resp.status_code}"
        except Exception as e:
            self.logger.error(f"get_mdblist_item exception: {e}", exc_info=True)
            return None, str(e)

    async def resolve_tmdb_id(self, item: dict, token: str) -> Optional[int]:
        """Attempts to find a TMDB ID for a Riven item using multiple strategies."""
        # 1. Direct field
        tmdb_id = item.get("tmdb_id")
        if tmdb_id:
            return int(tmdb_id)
            
        # 2. Parent IDs
        if "parent_ids" in item:
            tmdb_id = item["parent_ids"].get("tmdb_id")
            if tmdb_id:
                return int(tmdb_id)

        # 3. External lookup (TVDB or IMDB)
        media_type = item.get("type", "movie")
        external_id = item.get("tvdb_id") or (item.get("parent_ids") or {}).get("tvdb_id")
        source_type = "tvdb_id"
        
        if not external_id:
            external_id = item.get("imdb_id") or (item.get("parent_ids") or {}).get("imdb_id")
            source_type = "imdb_id"
            
        if not external_id:
            # For shows, the Riven ID is often the TVDB ID
            if media_type == "show":
                external_id = item.get("id")
                source_type = "tvdb_id"
            # For movies, the Riven ID is often the TMDB ID
            elif media_type == "movie":
                return int(item.get("id"))

        if external_id:
            resolved_id, _ = await self.find_tmdb_id(str(external_id), source_type, token)
            if resolved_id:
                return int(resolved_id)
                
        return None

    async def bulk_action(self, action: str, item_ids: List[str], riven_key: str):
        # action: remove, reset, retry
        url = f"{self.be_base_url}/api/v1/items/{action}"
        headers = {
            "x-api-key": riven_key,
            "Content-Type": "application/json",
            "accept": "*/*"
        }
        data = {"ids": item_ids}
        method = "DELETE" if action == "remove" else "POST"
        
        self.logger.info(f"BULK_ACTION_START: {method} {url} | IDS: {item_ids}")
        
        try:
            resp = await self.client.request(method, url, headers=headers, json=data)
            self.logger.info(f"BULK_ACTION_RESPONSE: Status {resp.status_code} | Body: {resp.text}")
            
            # The remove/retry endpoints often return 200 even if some IDs fail
            if resp.status_code == 200:
                return True, resp.json()
            else:
                return False, f"Status: {resp.status_code}, Body: {resp.text}"
        except Exception as e:
            self.logger.error(f"BULK_ACTION_EXCEPTION: {e}")
            return False, str(e)

    async def get_item_by_id(self, media_type: str, media_id: str, riven_key: str, extended: bool = False):
        url = f"{self.be_base_url}/api/v1/items/{media_id}"
        headers = {"x-api-key": riven_key}
        params = {"media_type": media_type}
        if extended:
            params["extended"] = "true"
        self.logger.info(f"get_item_by_id: URL={url}, Params={params}")
        try:
            resp = await self.client.get(url, headers=headers, params=params)
            self.logger.info(f"get_item_by_id: Status={resp.status_code}")
            return resp.json() if resp.status_code == 200 else None
        except Exception as e:
            self.logger.error(f"get_item_by_id Error: {e}")
            return None

    async def add_item(self, media_type: str, id_type: str, item_id: str, riven_key: str):
        url = f"{self.be_base_url}/api/v1/items/add"
        headers = {"x-api-key": riven_key}
        data = {"media_type": media_type, id_type: [str(item_id)]}
        self.logger.info(f"add_item: URL={url}, Data={data}")
        try:
            resp = await self.client.post(url, headers=headers, json=data)
            return (True, resp.json()) if resp.status_code == 200 else (False, f"Status: {resp.status_code}, Body: {resp.text}")
        except Exception as e:
            return (False, str(e))

    async def delete_item(self, item_id: int, riven_key: str):
        url = f"{self.be_base_url}/api/v1/items/remove"
        headers = {"x-api-key": riven_key}
        data = {"ids": [str(item_id)]}
        self.logger.info(f"delete_item: URL={url}, Data={data}")
        try:
            resp = await self.client.request("DELETE", url, headers=headers, json=data)
            return (True, resp.json()) if resp.status_code == 200 else (False, f"Status: {resp.status_code}, Body: {resp.text}")
        except Exception as e:
            return (False, str(e))

    async def reset_item(self, item_id: int, riven_key: str):
        url = f"{self.be_base_url}/api/v1/items/reset"
        headers = {"x-api-key": riven_key}
        data = {"ids": [str(item_id)]}
        self.logger.info(f"reset_item: URL={url}, Data={data}")
        try:
            resp = await self.client.post(url, headers=headers, json=data)
            return (True, resp.json()) if resp.status_code == 200 else (False, f"Status: {resp.status_code}, Body: {resp.text}")
        except Exception as e:
            return (False, str(e))

    async def retry_item(self, item_id: int, riven_key: str):
        url = f"{self.be_base_url}/api/v1/items/retry"
        headers = {"x-api-key": riven_key}
        data = {"ids": [str(item_id)]}
        self.logger.info(f"retry_item: URL={url}, Data={data}")
        try:
            resp = await self.client.post(url, headers=headers, json=data)
            return (True, resp.json()) if resp.status_code == 200 else (False, f"Status: {resp.status_code}, Body: {resp.text}")
        except Exception as e:
            return (False, str(e))

    async def get_items(self, riven_key: str, limit: int = 50, page: int = 1, sort: Optional[str] = None, search: Optional[str] = None, extended: bool = False, count_only: bool = False, item_type: Optional[str] = None, states: Optional[List[str]] = None, timeout: Optional[float] = None):
        url = f"{self.be_base_url}/api/v1/items"
        headers = {"x-api-key": riven_key}
        params = {
            "limit": limit,
            "page": page,
            "extended": extended,
            "count_only": count_only
        }
        if sort:
            params["sort"] = sort
        if search:
            params["search"] = search
        if item_type: # Add item_type to params if provided
            params["type"] = item_type
        if states:
            params["states"] = states
        
        self.logger.info(f"get_items: URL={url}, Params={params}")

        try:
            resp = await self.client.get(url, headers=headers, params=params, timeout=timeout)
            self.logger.info(f"get_items: Response status code: {resp.status_code}")
            if resp.status_code == 200:
                return resp.json(), None
            else:
                err_msg = f"Status: {resp.status_code}, Body: {resp.text}"
                self.logger.error(f"get_items: API Error: {err_msg}")
                return None, err_msg
        except httpx.TimeoutException as e:
            err_msg = f"Request timed out after {self.client.timeout}"
            self.logger.error(f"get_items: {err_msg} ({type(e).__name__})")
            return None, err_msg
        except httpx.ConnectError as e:
            err_msg = f"Connection to {e.request.url} failed."
            self.logger.error(f"get_items: {err_msg} ({type(e).__name__})")
            return None, err_msg
        except Exception as e:
            # Use repr(e) to ensure we see the error even if str(e) is empty
            err_msg = f"Unexpected error: {repr(e)}"
            self.logger.error(f"get_items: {err_msg}")
            return None, err_msg


    async def get_direct_logs(self, riven_key: str):
        url = f"{self.be_base_url}/api/v1/logs"
        headers = {"x-api-key": riven_key}
        try:
            resp = await self.client.get(url, headers=headers)
            if resp.status_code == 200:
                return resp.json().get("logs", []), None
            return None, f"Status: {resp.status_code}"
        except Exception as e:
            return None, str(e)

    async def upload_logs(self, riven_key: str):
        url = f"{self.be_base_url}/api/v1/upload_logs"
        headers = {"x-api-key": riven_key}
        self.logger.info(f"upload_logs: URL={url}")
        try:
            resp = await self.client.post(url, headers=headers)
            if resp.status_code == 200:
                return resp.json().get("url"), None
            return None, f"Status: {resp.status_code}, Body: {resp.text}"
        except Exception as e:
            return None, str(e)

    async def get_logs_from_url(self, url: str):
        self.logger.info(f"get_logs_from_url: URL={url}")
        try:
            resp = await self.client.get(url)
            if resp.status_code == 200:
                return resp.text, None
            return None, f"Status: {resp.status_code}, Body: {resp.text}"
        except Exception as e:
            return None, str(e)

    async def scrape_stream(self, media_type: str, tmdb_id: int, riven_key: str, item_id: str = None, tvdb_id: Optional[int] = None):
        url = f"{self.be_base_url}/api/v1/scrape/scrape_stream"
        if item_id:
            params = {"media_type": media_type, "item_id": item_id}
        elif media_type == "tv" and tvdb_id: # Use tvdb_id for TV shows if available and no item_id
            params = {"media_type": media_type, "tvdb_id": str(tvdb_id)}
        else: # Default to tmdb_id for movies, or if tvdb_id is not provided for TV
            params = {"media_type": media_type, "tmdb_id": str(tmdb_id)}

        headers = {"x-api-key": riven_key, "Accept": "text/event-stream"}
        
        self.logger.info(f"scrape_stream: URL={url}, Params={params}")

        try:
            async with self.client.stream("GET", url, headers=headers, params=params) as response:
                self.logger.info(f"scrape_stream: Response status code: {response.status_code}")
                if response.status_code != 200:
                    body = await response.aread()
                    self.logger.error(f"scrape_stream: Error: Status: {response.status_code}, Body: {body.decode()}")
                    yield f"error: Status: {response.status_code}, Body: {body.decode()}"
                    return
                async for line in response.aiter_lines():
        # self.logger.info(f"scrape_stream: Received line: {line}")
                    yield line
        except httpx.ConnectError as e:
            self.logger.error(f"scrape_stream: Connection error: {e}")
            yield f"error: Connection to {e.request.url} failed."
        except Exception as e:
            self.logger.error(f"scrape_stream: Unexpected error: {e}")
            yield f"error: {str(e)}"

    async def start_scrape_session(self, media_type: str, magnet: str, tmdb_id: int, riven_key: str, item_id: str = None, tvdb_id: Optional[int] = None):
        url = f"{self.be_base_url}/api/v1/scrape/start_session"
        params = {"media_type": media_type, "magnet": magnet}
        if item_id:
            params["item_id"] = item_id
        elif media_type == "tv" and tvdb_id:
            params["tvdb_id"] = str(tvdb_id)
        else:
            params["tmdb_id"] = str(tmdb_id)
        self.logger.info(f"start_scrape_session: URL={url}, Params={params}")
        try:
            resp = await self.client.post(url, headers={"x-api-key": riven_key, "Content-Length": "0"}, params=params)
            if resp.status_code == 200:
                return resp.json(), None
            return None, resp.json().get("detail", resp.text)
        except Exception as e:
            return None, str(e)

    async def select_scrape_file(self, session_id: str, file_metadata: dict, riven_key: str):
        url = f"{self.be_base_url}/api/v1/scrape/select_files/{session_id}"
        headers = {"x-api-key": riven_key}
        self.logger.info(f"select_scrape_file: URL={url}, Data={file_metadata}")
        try:
            resp = await self.client.post(url, headers=headers, json=file_metadata)
            return (True, resp.json()) if resp.status_code == 200 else (False, f"Status: {resp.status_code}, Body: {resp.text}")
        except Exception as e:
            return (False, str(e))

    async def update_scrape_attributes(self, session_id: str, file_metadata: dict, riven_key: str):
        url = f"{self.be_base_url}/api/v1/scrape/update_attributes/{session_id}"
        headers = {"x-api-key": riven_key}
        self.logger.info(f"update_scrape_attributes: URL={url}, Data={file_metadata}")
        try:
            resp = await self.client.post(url, headers=headers, json=file_metadata)
            return (True, resp.json()) if resp.status_code == 200 else (False, f"Status: {resp.status_code}, Body: {resp.text}")
        except Exception as e:
            return (False, str(e))

    async def complete_scrape_session(self, session_id: str, riven_key: str):
        url = f"{self.be_base_url}/api/v1/scrape/complete_session/{session_id}"
        headers = {"x-api-key": riven_key}
        self.logger.info(f"complete_scrape_session: URL={url}")
        try:
            resp = await self.client.post(url, headers=headers)
            return (True, resp.json()) if resp.status_code == 200 else (False, f"Status: {resp.status_code}, Body: {resp.text}")
        except Exception as e:
            return (False, str(e))

    async def abort_scrape_session(self, session_id: str, riven_key: str):
        url = f"{self.be_base_url}/api/v1/scrape/abort_session/{session_id}"
        headers = {"x-api-key": riven_key}
        self.logger.info(f"abort_scrape_session: URL={url}")
        try:
            resp = await self.client.post(url, headers=headers)
            return (True, resp.json()) if resp.status_code == 200 else (False, f"Status: {resp.status_code}, Body: {resp.text}")
        except Exception as e:
            return (False, str(e))

    async def parse_torrent_titles(self, titles: list, riven_key: str):
        url = f"{self.be_base_url}/api/v1/scrape/parse"
        headers = {"x-api-key": riven_key}
        self.logger.info(f"parse_torrent_titles: URL={url}, Data={titles}")
        try:
            resp = await self.client.post(url, headers=headers, json=titles)
            if resp.status_code == 200:
                return resp.json(), None
            return None, f"Status: {resp.status_code}, Body: {resp.text}"
        except Exception as e:
            return None, str(e)

    async def get_poster_chafa(self, poster_url: str, width: int = 80, height: Optional[int] = None):
        self.logger.debug(f"Rendering poster from {poster_url} with width {width} and height {height}")
        try:
            async with self.client.stream("GET", poster_url) as response:
                if response.status_code != 200:
                    return None, f"Failed to download image: Status {response.status_code}"

                size_arg = f"{width}x"
                if height:
                    size_arg = f"{width}x{height}"

                chafa_process = await asyncio.create_subprocess_exec(
                    "chafa", "--size", size_arg, "--colors", "256", "-",
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )

                async for chunk in response.aiter_bytes():
                    chafa_process.stdin.write(chunk)
                
                await chafa_process.stdin.drain()
                chafa_process.stdin.close()

                stdout, stderr = await chafa_process.communicate()

                if chafa_process.returncode != 0:
                    return None, f"Chafa error: {stderr.decode()}"
                
                return stdout.decode(), None

        except Exception as e:
            return None, str(e)

    async def search_tmdb(self, query: str, token: str):
        if not token or token == "YOUR_TOKEN_HERE":
            return (None, "TMDB Bearer Token not configured in settings.json")
            
        url = f"{self.tmdb_base_url}/search/multi"
        headers = {"Authorization": f"Bearer {token}", "accept": "application/json"}
        params = {"query": query, "include_adult": "false", "language": "en-US", "page": "1"}
        self.logger.info(f"search_tmdb: Query={query}")
        
        try:
            resp = await self.client.get(url, headers=headers, params=params)
            if resp.status_code == 200:
                raw_results = resp.json().get("results", [])
                processed_results = []
                for item in raw_results:
                    if item.get("media_type") == "person":
                        continue
                    
                    processed = {
                        "id": item.get("id"),
                        "media_type": item.get("media_type"),
                        "title": item.get("title") or item.get("name"),
                        "release_date": item.get("release_date") or item.get("first_air_date"),
                        "popularity": item.get("popularity"),
                        "vote_average": item.get("vote_average"),
                        "vote_count": item.get("vote_count"),
                        "overview": item.get("overview"),
                        "tagline": item.get("tagline"),
                        "genre_ids": item.get("genre_ids", []),
                        "original_language": item.get("original_language")
                    }
                    processed_results.append(processed)
                return (processed_results, None)
            else:
                return (None, f"TMDB search failed: Status {resp.status_code}, Body: {resp.text}")
        except Exception as e:
            return (None, str(e))

    async def get_tmdb_details(self, media_type: str, tmdb_id: int, token: str):
        if not token or token == "YOUR_TOKEN_HERE":
            return (None, "TMDB Bearer Token not configured in settings.json")

        url = f"{self.tmdb_base_url}/{media_type}/{tmdb_id}"
        headers = {"Authorization": f"Bearer {token}", "accept": "application/json"}
        params = {"append_to_response": "external_ids"}
        self.logger.info(f"get_tmdb_details: URL={url}, Params={params}")

        try:
            resp = await self.client.get(url, headers=headers, params=params)
            self.logger.info(f"get_tmdb_details: Status={resp.status_code}")
            if resp.status_code == 200:
                return (resp.json(), None)
            else:
                return (None, f"TMDB details failed: Status {resp.status_code}, Body: {resp.text}")
        except Exception as e:
            self.logger.error(f"get_tmdb_details Error: {e}")
            return (None, str(e))

    async def find_tmdb_id(self, external_id: str, source: str, token: str):
        if not token or token == "YOUR_TOKEN_HERE":
            return (None, "TMDB Bearer Token not configured in settings.json")
        
        url = f"{self.tmdb_base_url}/find/{external_id}"
        headers = {"Authorization": f"Bearer {token}", "accept": "application/json"}
        params = {"external_source": source}
        self.logger.info(f"find_tmdb_id: URL={url}, Params={params}")
        
        try:
            resp = await self.client.get(url, headers=headers, params=params)
            self.logger.info(f"find_tmdb_id: Status={resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                for key in ["movie_results", "tv_results"]:
                    if data.get(key):
                        return (data[key][0].get("id"), None)
                if data.get("tv_episode_results"):
                    return (data["tv_episode_results"][0].get("show_id"), None)
                if data.get("tv_season_results"):
                    return (data["tv_season_results"][0].get("show_id"), None)
                return (None, "No TMDB mapping found for this external ID")
            else:
                return (None, f"TMDB find failed: Status {resp.status_code}")
        except Exception as e:
            self.logger.error(f"find_tmdb_id Error: {e}")
            return (None, str(e))

    async def get_tmdb_trending(self, token: str, media_type: str = "all", time_window: str = "day", page: int = 1):
        if not token or token == "YOUR_TOKEN_HERE":
            return (None, "TMDB Bearer Token not configured")
        
        url = f"{self.tmdb_base_url}/trending/{media_type}/{time_window}"
        headers = {"Authorization": f"Bearer {token}", "accept": "application/json"}
        params = {"page": str(page)}
        self.logger.info(f"get_tmdb_trending: URL={url}, Page={page}")
        
        try:
            resp = await self.client.get(url, headers=headers, params=params)
            if resp.status_code == 200:
                return (resp.json().get("results", []), None)
            return (None, f"TMDB trending failed: Status {resp.status_code}")
        except Exception as e:
            return (None, str(e))

    async def get_stats(self, riven_key: str):
        url = f"{self.be_base_url}/api/v1/stats"
        headers = {"x-api-key": riven_key}
        self.logger.info(f"get_stats: URL={url}")
        try:
            resp = await self.client.get(url, headers=headers)
            self.logger.info(f"get_stats: Status={resp.status_code}")
            if resp.status_code == 200:
                return resp.json(), None
            return None, f"Status: {resp.status_code}"
        except Exception as e:
            return None, str(e)

    async def get_tmdb_genres(self, token: str):
        if not token or token == "YOUR_TOKEN_HERE":
            return {}, "TMDB Bearer Token not configured"
        
        genres_map = {}
        headers = {"Authorization": f"Bearer {token}", "accept": "application/json"}
        
        try:
            # Fetch Movie Genres
            movie_url = f"{self.tmdb_base_url}/genre/movie/list"
            m_resp = await self.client.get(movie_url, headers=headers)
            if m_resp.status_code == 200:
                for g in m_resp.json().get("genres", []):
                    genres_map[g["id"]] = g["name"]
            
            # Fetch TV Genres
            tv_url = f"{self.tmdb_base_url}/genre/tv/list"
            t_resp = await self.client.get(tv_url, headers=headers)
            if t_resp.status_code == 200:
                for g in t_resp.json().get("genres", []):
                    genres_map[g["id"]] = g["name"]
                    
            return genres_map, None
        except Exception as e:
            self.logger.error(f"get_tmdb_genres Error: {e}")
            return {}, str(e)

    async def get_services(self, riven_key: str):
        url = f"{self.be_base_url}/api/v1/services"
        headers = {"x-api-key": riven_key}
        try:
            resp = await self.client.get(url, headers=headers)
            if resp.status_code == 200:
                return resp.json(), None
            return None, f"Status: {resp.status_code}"
        except Exception as e:
            return None, str(e)

    async def get_health(self, riven_key: str):
        url = f"{self.be_base_url}/api/v1/health"
        headers = {"x-api-key": riven_key}
        self.logger.info(f"get_health: URL={url}")
        try:
            resp = await self.client.get(url, headers=headers)
            self.logger.info(f"get_health: Status={resp.status_code}")
            if resp.status_code == 200:
                return resp.json(), None
            return None, f"Status: {resp.status_code}"
        except Exception as e:
            return None, str(e)

    async def shutdown(self):
        await self.client.aclose()

    async def get_calendar(self, riven_key: str):
        url = f"{self.be_base_url}/api/v1/calendar"
        headers = {"x-api-key": riven_key}
        self.logger.info(f"get_calendar: URL={url}")
        try:
            resp = await self.client.get(url, headers=headers)
            if resp.status_code == 200:
                return resp.json(), None
            return None, f"Status: {resp.status_code}, Body: {resp.text}"
        except Exception as e:
            return None, str(e)

    async def get_settings(self, riven_key: str):
        url = f"{self.be_base_url}/api/v1/settings/get/all"
        headers = {"x-api-key": riven_key}
        self.logger.info(f"get_settings: URL={url}")
        try:
            resp = await self.client.get(url, headers=headers)
            if resp.status_code == 200:
                return resp.json(), None
            return None, f"Status: {resp.status_code}, Body: {resp.text}"
        except Exception as e:
            return None, str(e)

    async def update_settings(self, settings_data: dict, riven_key: str):
        url = f"{self.be_base_url}/api/v1/settings/set/all" 
        headers = {"x-api-key": riven_key}
        self.logger.info(f"update_settings: Sending payload to {url}: {settings_data}")
        try:
            resp = await self.client.post(url, headers=headers, json=settings_data)
            self.logger.info(f"update_settings: Status={resp.status_code}, Response={resp.text}")
            if resp.status_code == 200:
                return resp.json(), None
            return None, f"Status: {resp.status_code}, Body: {resp.text}"
        except Exception as e:
            self.logger.error(f"update_settings Error: {e}")
            return None, str(e)

    async def get_schema(self, riven_key: str):
        url = f"{self.be_base_url}/api/v1/settings/schema"
        headers = {"x-api-key": riven_key}
        self.logger.info(f"get_schema: URL={url}")
        try:
            resp = await self.client.get(url, headers=headers)
            if resp.status_code == 200:
                return resp.json(), None
            return None, f"Status: {resp.status_code}, Body: {resp.text}"
        except Exception as e:
            return None, str(e)
