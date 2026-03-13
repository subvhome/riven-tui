import httpx
import asyncio
import logging
import os
from typing import List, Optional

class RivenAPI:
    def __init__(self, be_base_url, fe_base_url, timeout=10.0):
        self.mdblist_api_key = "kgx75hvk95is39a6joe68tgux"
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Referer": f"{be_base_url}/scalar"
        }
        
        # PERFORMANCE FIX: Increased connection limits to prevent API flooding
        limits = httpx.Limits(max_keepalive_connections=50, max_connections=200)
        
        self.client = httpx.AsyncClient(
            follow_redirects=True, 
            timeout=timeout, 
            headers=headers,
            limits=limits
        )
        
        self.be_base_url = be_base_url
        self.fe_base_url = fe_base_url
        self.api_base_path = "/api/v1"
        self.tmdb_base_url = "https://api.themoviedb.org/3"
        self.mdblist_base_url = "https://api.mdblist.com"
        self.logger = logging.getLogger("Riven.API")
        self.logger.propagate = True
        self.chafa_semaphore = asyncio.Semaphore(3)

    async def get_mdblist_items(self, list_url_or_id: str):
        # Handle full URL or just the "user/listname" string
        path = list_url_or_id.replace("https://mdblist.com/lists/", "").replace("https://api.mdblist.com/lists/", "")
        path = path.strip("/")
        
        url = f"{self.mdblist_base_url}/lists/{path}/items/"
        all_mdb_items = {"movies": [], "shows": []}
        limit = 1000
        offset = 0
        
        while True:
            params = {
                "apikey": self.mdblist_api_key,
                "limit": limit,
                "offset": offset
            }
            
            self.logger.debug(f"get_mdblist_items: URL={url}, Offset={offset}")
            
            try:
                resp = await self.client.get(url, params=params)
                if resp.status_code != 200:
                    return None, f"Mdblist error: {resp.status_code} - {resp.text}"
                
                data = resp.json()
                movies = data.get("movies", [])
                shows = data.get("shows", [])
                
                # If no items are returned in this batch, we are done
                if not movies and not shows:
                    break
                    
                all_mdb_items["movies"].extend(movies)
                all_mdb_items["shows"].extend(shows)
                
                # Check if we received a full page; if not, we are at the end
                if len(movies) + len(shows) < limit:
                    break
                    
                offset += limit
                
                # Safety break to prevent infinite loops if the API behaves unexpectedly
                if offset > 50000: 
                    break
                    
            except Exception as e:
                self.logger.error(f"get_mdblist_items exception: {e}", exc_info=True)
                return None, str(e)
                
        return all_mdb_items, None

    async def resolve_tmdb_id(self, item: dict, token: str) -> Optional[int]:
        tmdb_id = item.get("tmdb_id") or (item.get("parent_ids") or {}).get("tmdb_id")
        if tmdb_id: return int(tmdb_id)
        
        media_type = item.get("type", "movie")
        external_id = item.get("tvdb_id") or (item.get("parent_ids") or {}).get("tvdb_id")
        if not external_id:
            external_id = item.get("imdb_id") or (item.get("parent_ids") or {}).get("imdb_id")
            source_type = "imdb_id"
        else:
            source_type = "tvdb_id"

        if not external_id:
            if media_type == "show": external_id = item.get("id"); source_type = "tvdb_id"
            elif media_type == "movie": return int(item.get("id"))

        if external_id:
            resolved_id, _ = await self.find_tmdb_id(str(external_id), source_type, token)
            if resolved_id: return int(resolved_id)
        return None

    async def bulk_action(self, action: str, item_ids: List[str], riven_key: str):
        url = f"{self.be_base_url}{self.api_base_path}/items/{action}"
        headers = {"x-api-key": str(riven_key or ""), "Content-Type": "application/json", "accept": "*/*"}
        method = "DELETE" if action == "remove" else "POST"
        try:
            resp = await self.client.request(method, url, headers=headers, json={"ids": item_ids})
            return (resp.status_code == 200), resp.json() if resp.status_code == 200 else resp.text
        except Exception as e: return False, str(e)

    async def get_item_by_id(self, media_type: str, media_id: str, riven_key: str, extended: bool = False):
        url = f"{self.be_base_url}{self.api_base_path}/items/{media_id}"
        params = {"media_type": media_type}
        if extended: params["extended"] = "true"
        try:
            resp = await self.client.get(url, headers={"x-api-key": str(riven_key)}, params=params)
            return resp.json() if resp.status_code == 200 else None
        except Exception as e: return None

    async def add_item(self, media_type: str, id_type: str, item_id: str, riven_key: str):
        url = f"{self.be_base_url}{self.api_base_path}/items/add"
        try:
            resp = await self.client.post(url, headers={"x-api-key": str(riven_key)}, json={"media_type": media_type, id_type: [str(item_id)]})
            return (resp.status_code == 200), resp.json()
        except Exception as e: return False, str(e)

    async def bulk_add_items(self, media_type: str, id_type: str, item_ids: List[str], riven_key: str):
        url = f"{self.be_base_url}{self.api_base_path}/items/add"
        data = {"media_type": media_type, "tmdb_ids": item_ids if id_type == "tmdb_ids" else [], "tvdb_ids": item_ids if id_type == "tvdb_ids" else []}
        try:
            resp = await self.client.post(url, headers={"x-api-key": str(riven_key)}, json=data)
            return (resp.status_code == 200), resp.json()
        except Exception as e: return False, str(e)

    async def delete_item(self, item_id: int, riven_key: str):
        return await self.bulk_action("remove", [str(item_id)], riven_key)

    async def reset_item(self, item_id: int, riven_key: str):
        return await self.bulk_action("reset", [str(item_id)], riven_key)

    async def retry_item(self, item_id: int, riven_key: str):
        return await self.bulk_action("retry", [str(item_id)], riven_key)

    async def get_items(self, riven_key: str, limit: int = 50, page: int = 1, sort: Optional[str] = None, search: Optional[str] = None, extended: bool = False, count_only: bool = False, item_type: Optional[str] = None, states: Optional[List[str]] = None, timeout: Optional[float] = None):
        url = f"{self.be_base_url}{self.api_base_path}/items"
        params = {"limit": limit, "page": page, "extended": extended, "count_only": count_only}
        if sort: params["sort"] = sort
        if search: params["search"] = search
        if item_type: params["type"] = item_type
        if states: params["states"] = states
        try:
            resp = await self.client.get(url, headers={"x-api-key": str(riven_key)}, params=params, timeout=timeout)
            return (resp.json(), None) if resp.status_code == 200 else (None, resp.text)
        except Exception as e: return None, str(e)

    async def get_direct_logs(self, riven_key: str):
        try:
            resp = await self.client.get(f"{self.be_base_url}{self.api_base_path}/logs", headers={"x-api-key": str(riven_key)})
            return (resp.json().get("logs", []), None) if resp.status_code == 200 else (None, "Error")
        except Exception as e: return None, str(e)

    async def upload_logs(self, riven_key: str):
        try:
            resp = await self.client.post(f"{self.be_base_url}{self.api_base_path}/upload_logs", headers={"x-api-key": str(riven_key)})
            return (resp.json().get("url"), None) if resp.status_code == 200 else (None, "Error")
        except Exception as e: return None, str(e)

    async def get_logs_from_url(self, url: str):
        try:
            resp = await self.client.get(url)
            return (resp.text, None) if resp.status_code == 200 else (None, "Error")
        except Exception as e: return None, str(e)

    async def login(self, username, password):
        """Emulates SvelteKit login with mandatory Origin headers to bypass CSRF protection."""
        base = self.fe_base_url.rstrip('/')
        url = f"{base}/auth/login?/login"
        
        headers = {
            "accept": "application/json",
            "content-type": "application/x-www-form-urlencoded",
            "x-sveltekit-action": "true",
            "Origin": base,  # CRITICAL: Must match ORIGIN env var in Docker
            "Referer": f"{base}/auth/login",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
        }
        
        data = {
            "username": username,
            "password": password,
            "__superform_id": "loginForm"
        }
        
        try:
            self.logger.info(f"Attempting FE Login: {url} with Origin: {base}")
            resp = await self.client.post(url, headers=headers, data=data)
            
            # SvelteKit returns cookies in the 'set-cookie' header
            token = self.client.cookies.get("riven.session_token")
            if token:
                self.logger.info("FE Login Successful: Session token acquired.")
                return True, token
            
            return False, f"Status {resp.status_code}. Body: {resp.text[:200]}"
        except Exception as e:
            return False, str(e)

    async def scrape_stream(self, media_type: str, tmdb_id: int, riven_key: str, item_id: str = None, tvdb_id: Optional[int] = None, overrides: dict = None):
        """Consume SSE stream. Yields raw lines for debugging."""
        import json
        base = self.fe_base_url.rstrip('/')
        url = f"{base}/api/scrape_stream"
        params = {"media_type": media_type, "tmdb_id": str(tmdb_id)}
        if item_id: params["item_id"] = str(item_id)
        if tvdb_id: params["tvdb_id"] = str(tvdb_id)
        if overrides: params["ranking_overrides"] = json.dumps(overrides, separators=(',', ':'))

        headers = {"Accept": "text/event-stream", "Cache-Control": "no-cache", "Connection": "keep-alive"}
        try:
            async with self.client.stream("GET", url, headers=headers, params=params, timeout=120.0) as response:
                if response.status_code != 200:
                    yield f"error: HTTP {response.status_code}. Body: {await response.aread()}"
                    return
                async for line in response.aiter_lines():
                    yield line
        except Exception as e:
            yield f"error: {str(e)}"

    async def start_scrape_session(self, media_type: str, magnet: str, tmdb_id: int, riven_key: str, riven_item_id: str = None, tvdb_id: Optional[int] = None):
        """Initializes session. Endpoint: /api/v1/scrape/start_session (Requires v1)"""
        base = self.be_base_url.rstrip('/')
        url = f"{base}/api/v1/scrape/start_session"
        
        params = {
            "media_type": media_type,
            "magnet": magnet,
            "tmdb_id": str(tmdb_id)
        }
        if riven_item_id:
            params["item_id"] = str(riven_item_id)
        if tvdb_id:
            params["tvdb_id"] = str(tvdb_id)

        headers = {"x-api-key": riven_key}
        self.logger.info(f"SESSION START: {url} | Params: {params}")
        
        try:
            resp = await self.client.post(url, headers=headers, params=params)
            if resp.status_code == 200:
                return resp.json(), None
            return None, f"Status: {resp.status_code}, Body: {resp.text}"
        except Exception as e:
            return None, str(e)

    async def parse_torrent_titles(self, titles: list, riven_key: str):
        try:
            resp = await self.client.post(f"{self.be_base_url}{self.api_base_path}/scrape/parse", headers={"x-api-key": str(riven_key)}, json=titles)
            return (resp.json(), None) if resp.status_code == 200 else (None, "Error")
        except Exception as e: return None, str(e)

    async def get_poster_chafa(self, poster_url: str, width: int = 80, height: Optional[int] = None):
        # NEW: Put the whole process inside the semaphore block
        async with self.chafa_semaphore:
            try:
                async with self.client.stream("GET", poster_url) as response:
                    if response.status_code != 200: return None, "Error"
                    size = f"{width}x{height}" if height else f"{width}x"
                    env = os.environ.copy()
                    env["TERM"] = "xterm-256color"
                    process = await asyncio.create_subprocess_exec(
                        "chafa", "--format", "symbols", "--size", size, "-",
                        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env
                    )
                    async for chunk in response.aiter_bytes(): process.stdin.write(chunk)
                    await process.stdin.drain()
                    process.stdin.close()
                    stdout, _ = await process.communicate()
                    return stdout.decode(), None
            except Exception as e: 
                return None, str(e)

    async def search_tmdb(self, query: str, token: str):
        try:
            resp = await self.client.get(f"{self.tmdb_base_url}/search/multi", headers={"Authorization": f"Bearer {token}"}, params={"query": query, "include_adult": "false"})
            if resp.status_code == 200:
                results = [i for i in resp.json().get("results", []) if i.get("media_type") != "person"]
                return results, None
            return None, "Error"
        except Exception as e: return None, str(e)

    async def get_tmdb_details(self, media_type: str, tmdb_id: int, token: str):
        try:
            resp = await self.client.get(f"{self.tmdb_base_url}/{media_type}/{tmdb_id}", headers={"Authorization": f"Bearer {token}"}, params={"append_to_response": "external_ids"})
            return (resp.json(), None) if resp.status_code == 200 else (None, "Error")
        except Exception as e: return None, str(e)

    async def find_tmdb_id(self, external_id: str, source: str, token: str):
        url = f"{self.tmdb_base_url}/find/{external_id}"
        try:
            resp = await self.client.get(url, headers={"Authorization": f"Bearer {token}"}, params={"external_source": source})
            if resp.status_code == 200:
                data = resp.json()
                for key in ["movie_results", "tv_results"]:
                    if data.get(key): return data[key][0].get("id"), None
            return None, "Not found"
        except Exception as e: return None, str(e)

    async def get_tmdb_trending(self, token: str):
        try:
            resp = await self.client.get(f"{self.tmdb_base_url}/trending/all/day", headers={"Authorization": f"Bearer {token}"})
            return (resp.json().get("results", []), None) if resp.status_code == 200 else (None, "Error")
        except Exception as e: return None, str(e)

    async def get_stats(self, riven_key: str):
        try:
            resp = await self.client.get(f"{self.be_base_url}{self.api_base_path}/stats", headers={"x-api-key": str(riven_key)})
            return (resp.json(), None) if resp.status_code == 200 else (None, "Error")
        except Exception as e: return None, str(e)

    async def get_tmdb_genres(self, token: str):
        genres = {}
        try:
            for t in ["movie", "tv"]:
                r = await self.client.get(f"{self.tmdb_base_url}/genre/{t}/list", headers={"Authorization": f"Bearer {token}"})
                if r.status_code == 200:
                    for g in r.json().get("genres", []): genres[g["id"]] = g["name"]
            return genres, None
        except Exception as e: return {}, str(e)

    async def get_services(self, riven_key: str):
        try:
            resp = await self.client.get(f"{self.be_base_url}{self.api_base_path}/services", headers={"x-api-key": str(riven_key)})
            return (resp.json(), None) if resp.status_code == 200 else (None, "Error")
        except Exception as e: return None, str(e)

    async def get_health(self, riven_key: str):
        try:
            resp = await self.client.get(f"{self.be_base_url}{self.api_base_path}/health", headers={"x-api-key": str(riven_key)})
            return (resp.json(), None) if resp.status_code == 200 else (None, "Error")
        except Exception as e: return None, str(e)

    async def shutdown(self):
        await self.client.aclose()

    async def get_calendar(self, riven_key: str):
        try:
            resp = await self.client.get(f"{self.be_base_url}{self.api_base_path}/calendar", headers={"x-api-key": str(riven_key)})
            return (resp.json(), None) if resp.status_code == 200 else (None, "Error")
        except Exception as e: return None, str(e)

    async def get_settings(self, riven_key: str, use_fe: bool = False):
        """Fetches settings. If use_fe is True, uses the Frontend port for session priming."""
        # Determine which port to use. For scraping, we need to prime the FE port (33000).
        base = self.fe_base_url.rstrip('/') if use_fe else self.be_base_url.rstrip('/')
        url = f"{base}{self.api_base_path}/settings/get/all"
        
        headers = {"x-api-key": str(riven_key or "")}
        
        try:
            resp = await self.client.get(url, headers=headers, timeout=self.client.timeout)
            if resp.status_code == 200:
                return resp.json(), None
            # Return the actual status code if it's not 200
            return None, f"HTTP {resp.status_code} from {url}"
        except Exception as e:
            # Return the actual technical error (Timeout, Connection Refused, etc.)
            return None, f"{type(e).__name__}: {str(e)}"

    async def update_settings(self, settings_data: dict, riven_key: str):
        try:
            resp = await self.client.post(f"{self.be_base_url}{self.api_base_path}/settings/set/all", headers={"x-api-key": str(riven_key)}, json=settings_data)
            return (resp.json(), None) if resp.status_code == 200 else (None, "Error")
        except Exception as e: return None, str(e)

    async def get_schema(self, riven_key: str):
        try:
            resp = await self.client.get(f"{self.be_base_url}{self.api_base_path}/settings/schema", headers={"x-api-key": str(riven_key)})
            return (resp.json(), None) if resp.status_code == 200 else (None, "Error")
        except Exception as e: return None, str(e)
    
    async def scrape_session_action(self, session_id: str, action: str, riven_key: str, data: dict = None):
        """Unified replacement for all scrape session actions."""
        url = f"{self.be_base_url}{self.api_base_path}/scrape/session/{session_id}"
        headers = {"x-api-key": str(riven_key or ""), "Content-Type": "application/json"}
        
        payload = {"action": action}
        if data:
            payload.update(data)
            
        try:
            resp = await self.client.post(url, headers=headers, json=payload)
            return (resp.status_code == 200), resp.json() if resp.status_code == 200 else resp.text
        except Exception as e:
            return False, str(e)
    
    
