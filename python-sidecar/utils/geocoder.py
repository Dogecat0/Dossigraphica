import json
import os
import logging
import httpx
import asyncio
import time

logger = logging.getLogger(__name__)

class Geocoder:
    """
    Programmatic geocoder that uses local country data and external APIs 
    to provide fallback coordinates.
    """
    def __init__(self):
        self.country_map = {}
        self._load_countries()
        self._nominatim_semaphore = None
        self._pacing_lock = None
        self._last_request_time = 0.0
        self.nominatim_cache = {}
        self._load_cache()

    def _load_cache(self):
        try:
            cache_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "geocoder_cache.json")
            if os.path.exists(cache_path):
                with open(cache_path, 'r') as f:
                    self.nominatim_cache = json.load(f)
                logger.debug(f"Loaded {len(self.nominatim_cache)} cached geocoder entries.")
        except Exception as e:
            logger.error(f"Failed to load geocoder cache: {e}")
            self.nominatim_cache = {}

    def _save_cache(self):
        try:
            cache_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "geocoder_cache.json")
            with open(cache_path, 'w') as f:
                json.dump(self.nominatim_cache, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save geocoder cache: {e}")

    def _load_countries(self):
        try:
            # Workspace root relative to python-sidecar is ../
            path = os.path.join(os.path.dirname(__file__), "../../public/data/countries.json")
            if not os.path.exists(path):
                logger.warning(f"Countries data not found at {path}")
                return

            with open(path, 'r') as f:
                data = json.load(f)
                for feature in data.get("features", []):
                    props = feature.get("properties", {})
                    name = props.get("NAME")
                    bbox = feature.get("bbox") # [min_lng, min_lat, max_lng, max_lat]
                    
                    if name and bbox and len(bbox) == 4:
                        # Calculate centroid from bbox
                        lng = (bbox[0] + bbox[2]) / 2
                        lat = (bbox[1] + bbox[3]) / 2
                        self.country_map[name.lower()] = {"lat": lat, "lng": lng}
                        
                        # Also map some common variants or ISO codes if available
                        iso_a2 = props.get("ISO_A2")
                        if iso_a2:
                            self.country_map[iso_a2.lower()] = {"lat": lat, "lng": lng}
                        
                        iso_a3 = props.get("ISO_A3")
                        if iso_a3:
                            self.country_map[iso_a3.lower()] = {"lat": lat, "lng": lng}

            logger.info(f"Geocoder initialized with {len(self.country_map)} country entries.")
        except Exception as e:
            logger.error(f"Failed to load countries for geocoding: {e}")

    async def get_coords_async(self, location_string: str = None, city: str = None, country: str = None):
        """
        Asynchronously resolves a location string to coordinates.
        Uses local country centroids as a fast fallback and Nominatim for specific cities.
        """
        if not location_string and not (city or country):
            return None
        
        # Determine the cache/lookup key
        if location_string:
            name_clean = location_string.strip().lower()
        else:
            name_clean = ", ".join(filter(None, [city, country])).strip().lower()
        
        # 1. Local Country Match (fast/offline) - Only if it's a simple string without comma
        if "," not in name_clean:
            country_coords = self.get_country_coords(name_clean)
            if country_coords:
                return country_coords

        # 2. External Nominatim API for specific Cities or unmatched countries
        if name_clean in self.nominatim_cache:
            return self.nominatim_cache[name_clean]

        if self._nominatim_semaphore is None:
            self._nominatim_semaphore = asyncio.Semaphore(1)
            self._pacing_lock = asyncio.Lock()

        try:
            async with self._nominatim_semaphore:
                async with self._pacing_lock:
                    now = time.time()
                    elapsed = now - self._last_request_time
                    if elapsed < 2.0:
                        await asyncio.sleep(2.0 - elapsed)
                    self._last_request_time = time.time()

                # Nominatim REQUIRES a User-Agent
                headers = {"User-Agent": "Dossigraphica-Geocoder/1.0 (local-research-agent)"}
                email = os.getenv("NOMINATIM_EMAIL")
                
                async with httpx.AsyncClient(timeout=10.0) as client:
                    params = {
                        "format": "jsonv2",
                        "limit": 1
                    }
                    if email:
                        params["email"] = email
                    
                    # Prefer structured query if both city and country are present
                    if city and country:
                        params["city"] = city
                        params["country"] = country
                    else:
                        params["q"] = location_string or name_clean

                    response = await client.get("https://nominatim.openstreetmap.org/search", params=params, headers=headers)
                    response.raise_for_status()
                    data = response.json()
                
                if data:
                    res = data[0]
                    importance = float(res.get("importance", 0))
                    rank = int(res.get("place_rank", 0))
                    
                    # Verified if high importance AND specific enough (City level 15 or better)
                    is_specific = rank >= 15
                    
                    coords = {
                        "lat": float(res["lat"]),
                        "lng": float(res["lon"]),
                        "display_name": res.get("display_name"),
                        "confidence": "verified" if (importance > 0.6 and is_specific) else "city_center_approximation"
                    }
                    self.nominatim_cache[name_clean] = coords
                    self._save_cache()
                    return coords
                else:
                    self.nominatim_cache[name_clean] = None
                    self._save_cache()
        except Exception as e:
            logger.warning(f"External geocoding failed for '{name_clean}': {e}")

        # 3. Final Fallback to Country Centroid if Nominatim fails or for "City, Country"
        if "," in name_clean:
            country_part = name_clean.split(",")[-1].strip()
            return self.get_country_coords(country_part)

        return self.get_country_coords(name_clean)

    def get_country_coords(self, country_name: str):
        """Synchronous local country lookup."""
        if not country_name:
            return None
        
        name_clean = country_name.strip().lower()
        # Direct match
        if name_clean in self.country_map:
            return self.country_map[name_clean]
        
        # Fuzzy match (handle things like "USA" vs "United States")
        if "united states" in name_clean or name_clean == "usa":
            return self.country_map.get("united states of america") or self.country_map.get("us")
        if "china" in name_clean:
            return self.country_map.get("china")
        if "taiwan" in name_clean:
            return self.country_map.get("taiwan")
        
        return None

geocoder = Geocoder()
