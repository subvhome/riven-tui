import httpx
import asyncio
import logging
from typing import List, Optional

class RivenAPI:
    def __init__(self, be_base_url, timeout=10.0):
        self.client = httpx.AsyncClient(follow_redirects=True, timeout=timeout)
        self.be_base_url = be_base_url
        self.tmdb_base_url = "https://api.themoviedb.org/3"
        self.logger = logging.getLogger("RivenAPI")
        if not self.logger.handlers:
            handler = logging.FileHandler('api.log')
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

    async def get_item_by_id(self, media_type: str, media_id: str, api_key: str):
        url = f"{self.be_base_url}/api/v1/items/{media_id}"
        headers = {"x-api-key": api_key}
        params = {"media_type": media_type}
        self.logger.info(f"get_item_by_id: URL={url}, Params={params}")
        try:
            resp = await self.client.get(url, headers=headers, params=params)
            self.logger.info(f"get_item_by_id: Status={resp.status_code}")
            return resp.json() if resp.status_code == 200 else None
        except Exception as e:
            self.logger.error(f"get_item_by_id Error: {e}")
            return None

    async def add_item(self, media_type: str, id_type: str, item_id: str, api_key: str):
        url = f"{self.be_base_url}/api/v1/items/add"
        headers = {"x-api-key": api_key}
        data = {"media_type": media_type, id_type: [str(item_id)]}
        try:
            resp = await self.client.post(url, headers=headers, json=data)
            return (True, resp.json()) if resp.status_code == 200 else (False, f"Status: {resp.status_code}, Body: {resp.text}")
        except Exception as e:
            return (False, str(e))

    async def delete_item(self, item_id: int, api_key: str):
        url = f"{self.be_base_url}/api/v1/items/remove"
        headers = {"x-api-key": api_key}
        data = {"ids": [str(item_id)]}
        try:
            resp = await self.client.request("DELETE", url, headers=headers, json=data)
            return (True, resp.json()) if resp.status_code == 200 else (False, f"Status: {resp.status_code}, Body: {resp.text}")
        except Exception as e:
            return (False, str(e))

    async def reset_item(self, item_id: int, api_key: str):
        url = f"{self.be_base_url}/api/v1/items/reset"
        headers = {"x-api-key": api_key}
        data = {"ids": [str(item_id)]}
        try:
            resp = await self.client.post(url, headers=headers, json=data)
            return (True, resp.json()) if resp.status_code == 200 else (False, f"Status: {resp.status_code}, Body: {resp.text}")
        except Exception as e:
            return (False, str(e))

    async def retry_item(self, item_id: int, api_key: str):
        url = f"{self.be_base_url}/api/v1/items/retry"
        headers = {"x-api-key": api_key}
        data = {"ids": [str(item_id)]}
        try:
            resp = await self.client.post(url, headers=headers, json=data)
            return (True, resp.json()) if resp.status_code == 200 else (False, f"Status: {resp.status_code}, Body: {resp.text}")
        except Exception as e:
            return (False, str(e))

    async def get_items(self, api_key: str, limit: int = 50, page: int = 1, sort: Optional[str] = None, search: Optional[str] = None, extended: bool = False, count_only: bool = False, item_type: Optional[str] = None, states: Optional[List[str]] = None):
        url = f"{self.be_base_url}/api/v1/items"
        headers = {"x-api-key": api_key}
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
        
        self.logger.info(f"get_items: URL={url}, Params={params}, Headers={headers}")

        try:
            resp = await self.client.get(url, headers=headers, params=params)
            self.logger.info(f"get_items: Response status code: {resp.status_code}")
            if resp.status_code == 200:
                return resp.json(), None
            else:
                return None, f"Status: {resp.status_code}, Body: {resp.text}"
        except httpx.ConnectError as e:
            self.logger.error(f"get_items: Connection error: {e}")
            return None, f"Connection to {e.request.url} failed."
        except Exception as e:
            self.logger.error(f"get_items: Unexpected error: {e}")
            return None, str(e)


    async def upload_logs(self, api_key: str):
        url = f"{self.be_base_url}/api/v1/upload_logs"
        headers = {"x-api-key": api_key}
        try:
            resp = await self.client.post(url, headers=headers)
            if resp.status_code == 200:
                return resp.json().get("url"), None
            return None, f"Status: {resp.status_code}, Body: {resp.text}"
        except Exception as e:
            return None, str(e)

    async def get_logs_from_url(self, url: str):
        try:
            resp = await self.client.get(url)
            if resp.status_code == 200:
                return resp.text, None
            return None, f"Status: {resp.status_code}, Body: {resp.text}"
        except Exception as e:
            return None, str(e)

    async def scrape_stream(self, media_type: str, tmdb_id: int, api_key: str, item_id: str = None, tvdb_id: Optional[int] = None):
        url = f"{self.be_base_url}/api/v1/scrape/scrape_stream"
        if item_id:
            params = {"media_type": media_type, "item_id": item_id}
        elif media_type == "tv" and tvdb_id: # Use tvdb_id for TV shows if available and no item_id
            params = {"media_type": media_type, "tvdb_id": str(tvdb_id)}
        else: # Default to tmdb_id for movies, or if tvdb_id is not provided for TV
            params = {"media_type": media_type, "tmdb_id": str(tmdb_id)}

        headers = {"x-api-key": api_key, "Accept": "text/event-stream"}
        
        self.logger.info(f"scrape_stream: URL={url}, Params={params}, Headers={headers}")

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

    async def start_scrape_session(self, media_type: str, magnet: str, tmdb_id: int, api_key: str, item_id: str = None, tvdb_id: Optional[int] = None):
        url = f"{self.be_base_url}/api/v1/scrape/start_session"
        params = {"media_type": media_type, "magnet": magnet}
        if item_id:
            params["item_id"] = item_id
        elif media_type == "tv" and tvdb_id:
            params["tvdb_id"] = str(tvdb_id)
        else:
            params["tmdb_id"] = str(tmdb_id)
            
        try:
            # Riven requires a POST with 0 content-length and params in URL
            resp = await self.client.post(url, headers={"x-api-key": api_key, "Content-Length": "0"}, params=params)
            if resp.status_code == 200:
                return resp.json(), None
            return None, resp.json().get("detail", resp.text)
        except Exception as e:
            return None, str(e)

    async def select_scrape_file(self, session_id: str, file_metadata: dict, api_key: str):
        url = f"{self.be_base_url}/api/v1/scrape/select_files/{session_id}"
        headers = {"x-api-key": api_key}
        try:
            resp = await self.client.post(url, headers=headers, json=file_metadata)
            return (True, resp.json()) if resp.status_code == 200 else (False, f"Status: {resp.status_code}, Body: {resp.text}")
        except Exception as e:
            return (False, str(e))

    async def update_scrape_attributes(self, session_id: str, file_metadata: dict, api_key: str):
        url = f"{self.be_base_url}/api/v1/scrape/update_attributes/{session_id}"
        headers = {"x-api-key": api_key}
        try:
            resp = await self.client.post(url, headers=headers, json=file_metadata)
            return (True, resp.json()) if resp.status_code == 200 else (False, f"Status: {resp.status_code}, Body: {resp.text}")
        except Exception as e:
            return (False, str(e))

    async def complete_scrape_session(self, session_id: str, api_key: str):
        url = f"{self.be_base_url}/api/v1/scrape/complete_session/{session_id}"
        headers = {"x-api-key": api_key}
        try:
            resp = await self.client.post(url, headers=headers)
            return (True, resp.json()) if resp.status_code == 200 else (False, f"Status: {resp.status_code}, Body: {resp.text}")
        except Exception as e:
            return (False, str(e))

    async def abort_scrape_session(self, session_id: str, api_key: str):
        url = f"{self.be_base_url}/api/v1/scrape/abort_session/{session_id}"
        headers = {"x-api-key": api_key}
        try:
            resp = await self.client.post(url, headers=headers)
            return (True, resp.json()) if resp.status_code == 200 else (False, f"Status: {resp.status_code}, Body: {resp.text}")
        except Exception as e:
            return (False, str(e))

    async def parse_torrent_titles(self, titles: list, api_key: str):
        url = f"{self.be_base_url}/api/v1/scrape/parse"
        headers = {"x-api-key": api_key}
        try:
            resp = await self.client.post(url, headers=headers, json=titles)
            if resp.status_code == 200:
                return resp.json(), None # Return (data, None) on success
            return None, f"Status: {resp.status_code}, Body: {resp.text}"
        except Exception as e:
            return None, str(e)


    async def get_poster_chafa(self, poster_url: str, width: int = 80):
        self.logger.info(f"Rendering poster from {poster_url} with width {width}")
        try:
            async with self.client.stream("GET", poster_url) as response:
                if response.status_code != 200:
                    return None, f"Failed to download image: Status {response.status_code}"

                chafa_process = await asyncio.create_subprocess_exec(
                    "chafa", "--size", f"{width}x", "--colors", "256", "-",
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
        
        try:
            resp = await self.client.get(url, headers=headers, params=params)
            if resp.status_code == 200:
                # Process the results to a consistent format
                raw_results = resp.json().get("results", [])
                processed_results = []
                for item in raw_results:
                    # Skip people
                    if item.get("media_type") == "person":
                        continue
                    
                    processed = {
                        "id": item.get("id"),
                        "media_type": item.get("media_type"),
                        "title": item.get("title") or item.get("name"),
                        "release_date": item.get("release_date") or item.get("first_air_date"),
                        "popularity": item.get("popularity"),
                        "vote_count": item.get("vote_count"),
                        "overview": item.get("overview")
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
        """Finds a TMDB ID using an external ID (imdb_id, tvdb_id)."""
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
                return (None, "No TMDB mapping found for this external ID")
            else:
                return (None, f"TMDB find failed: Status {resp.status_code}")
        except Exception as e:
            self.logger.error(f"find_tmdb_id Error: {e}")
            return (None, str(e))

    async def shutdown(self):
        """Closes the httpx client."""
        await self.client.aclose()

    async def get_calendar(self, api_key: str):
        url = f"{self.be_base_url}/api/v1/calendar"
        headers = {"x-api-key": api_key}
        try:
            resp = await self.client.get(url, headers=headers)
            if resp.status_code == 200:
                return resp.json(), None
            return None, f"Status: {resp.status_code}, Body: {resp.text}"
        except Exception as e:
            return None, str(e)
