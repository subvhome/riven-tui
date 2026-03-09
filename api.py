import httpx
import asyncio
import logging
import os
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
        self.api_base_path = "/api/v1"
        self.tmdb_base_url = "https://api.themoviedb.org/3"
        self.mdblist_base_url = "https://api.mdblist.com"
        self.logger = logging.getLogger("Riven.API")
        self.logger.propagate = True

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
        except: return None

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
        except: return False, "Error"

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
        except: return None, "Error"

    async def upload_logs(self, riven_key: str):
        try:
            resp = await self.client.post(f"{self.be_base_url}{self.api_base_path}/upload_logs", headers={"x-api-key": str(riven_key)})
            return (resp.json().get("url"), None) if resp.status_code == 200 else (None, "Error")
        except: return None, "Error"

    async def get_logs_from_url(self, url: str):
        try:
            resp = await self.client.get(url)
            return (resp.text, None) if resp.status_code == 200 else (None, "Error")
        except: return None, "Error"

    async def scrape_stream(self, media_type: str, tmdb_id: int, riven_key: str, item_id: str = None, tvdb_id: Optional[int] = None):
        url = f"{self.be_base_url}/api/scrape_stream"
        params = {"media_type": media_type}
        if item_id: params["item_id"] = item_id
        elif media_type == "tv" and tvdb_id: params["tvdb_id"] = str(tvdb_id)
        else: params["tmdb_id"] = str(tmdb_id)
        try:
            async with self.client.stream("GET", url, headers={"x-api-key": riven_key, "Accept": "text/event-stream"}, params=params) as response:
                if response.status_code != 200: return
                async for line in response.aiter_lines(): yield line
        except: yield "error: Connection failed"

    async def start_scrape_session(self, media_type: str, magnet: str, tmdb_id: int, riven_key: str, item_id: str = None, tvdb_id: Optional[int] = None):
        url = f"{self.be_base_url}{self.api_base_path}/scrape/start_session"
        params = {"media_type": media_type, "magnet": magnet}
        if item_id: params["item_id"] = item_id
        elif media_type == "tv" and tvdb_id: params["tvdb_id"] = str(tvdb_id)
        else: params["tmdb_id"] = str(tmdb_id)
        try:
            resp = await self.client.post(url, headers={"x-api-key": riven_key}, params=params)
            return (resp.json(), None) if resp.status_code == 200 else (None, resp.text)
        except Exception as e: return None, str(e)

    async def select_scrape_file(self, session_id: str, file_metadata: dict, riven_key: str):
        url = f"{self.be_base_url}{self.api_base_path}/scrape/select_files/{session_id}"
        try:
            resp = await self.client.post(url, headers={"x-api-key": str(riven_key)}, json=file_metadata)
            return (resp.status_code == 200), resp.json()
        except: return False, "Error"

    async def update_scrape_attributes(self, session_id: str, file_metadata: dict, riven_key: str):
        url = f"{self.be_base_url}{self.api_base_path}/scrape/update_attributes/{session_id}"
        try:
            resp = await self.client.post(url, headers={"x-api-key": str(riven_key)}, json=file_metadata)
            return (resp.status_code == 200), resp.json()
        except: return False, "Error"

    async def complete_scrape_session(self, session_id: str, riven_key: str):
        try:
            resp = await self.client.post(f"{self.be_base_url}{self.api_base_path}/scrape/complete_session/{session_id}", headers={"x-api-key": str(riven_key)})
            return (resp.status_code == 200), resp.json()
        except: return False, "Error"

    async def abort_scrape_session(self, session_id: str, riven_key: str):
        try:
            resp = await self.client.post(f"{self.be_base_url}{self.api_base_path}/scrape/abort_session/{session_id}", headers={"x-api-key": str(riven_key)})
            return (resp.status_code == 200), resp.json()
        except: return False, "Error"

    async def parse_torrent_titles(self, titles: list, riven_key: str):
        try:
            resp = await self.client.post(f"{self.be_base_url}{self.api_base_path}/scrape/parse", headers={"x-api-key": str(riven_key)}, json=titles)
            return (resp.json(), None) if resp.status_code == 200 else (None, "Error")
        except: return None, "Error"

    async def get_poster_chafa(self, poster_url: str, width: int = 80, height: Optional[int] = None):
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
        except Exception as e: return None, str(e)

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
        except: return None, "Error"

    async def find_tmdb_id(self, external_id: str, source: str, token: str):
        url = f"{self.tmdb_base_url}/find/{external_id}"
        try:
            resp = await self.client.get(url, headers={"Authorization": f"Bearer {token}"}, params={"external_source": source})
            if resp.status_code == 200:
                data = resp.json()
                for key in ["movie_results", "tv_results"]:
                    if data.get(key): return data[key][0].get("id"), None
            return None, "Not found"
        except: return None, "Error"

    async def get_tmdb_trending(self, token: str):
        try:
            resp = await self.client.get(f"{self.tmdb_base_url}/trending/all/day", headers={"Authorization": f"Bearer {token}"})
            return (resp.json().get("results", []), None) if resp.status_code == 200 else (None, "Error")
        except: return None, "Error"

    async def get_stats(self, riven_key: str):
        try:
            resp = await self.client.get(f"{self.be_base_url}{self.api_base_path}/stats", headers={"x-api-key": str(riven_key)})
            return (resp.json(), None) if resp.status_code == 200 else (None, "Error")
        except: return None, "Error"

    async def get_tmdb_genres(self, token: str):
        genres = {}
        try:
            for t in ["movie", "tv"]:
                r = await self.client.get(f"{self.tmdb_base_url}/genre/{t}/list", headers={"Authorization": f"Bearer {token}"})
                if r.status_code == 200:
                    for g in r.json().get("genres", []): genres[g["id"]] = g["name"]
            return genres, None
        except: return {}, "Error"

    async def get_services(self, riven_key: str):
        try:
            resp = await self.client.get(f"{self.be_base_url}{self.api_base_path}/services", headers={"x-api-key": str(riven_key)})
            return (resp.json(), None) if resp.status_code == 200 else (None, "Error")
        except: return None, "Error"

    async def get_health(self, riven_key: str):
        try:
            resp = await self.client.get(f"{self.be_base_url}{self.api_base_path}/health", headers={"x-api-key": str(riven_key)})
            return (resp.json(), None) if resp.status_code == 200 else (None, "Error")
        except: return None, "Error"

    async def shutdown(self):
        await self.client.aclose()

    async def get_calendar(self, riven_key: str):
        try:
            resp = await self.client.get(f"{self.be_base_url}{self.api_base_path}/calendar", headers={"x-api-key": str(riven_key)})
            return (resp.json(), None) if resp.status_code == 200 else (None, "Error")
        except: return None, "Error"

    async def get_settings(self, riven_key: str):
        try:
            resp = await self.client.get(f"{self.be_base_url}{self.api_base_path}/settings/get/all", headers={"x-api-key": str(riven_key)})
            return (resp.json(), None) if resp.status_code == 200 else (None, "Error")
        except: return None, "Error"

    async def update_settings(self, settings_data: dict, riven_key: str):
        try:
            resp = await self.client.post(f"{self.be_base_url}{self.api_base_path}/settings/set/all", headers={"x-api-key": str(riven_key)}, json=settings_data)
            return (resp.json(), None) if resp.status_code == 200 else (None, "Error")
        except: return None, "Error"

    async def get_schema(self, riven_key: str):
        try:
            resp = await self.client.get(f"{self.be_base_url}{self.api_base_path}/settings/schema", headers={"x-api-key": str(riven_key)})
            return (resp.json(), None) if resp.status_code == 200 else (None, "Error")
        except: return None, "Error"
