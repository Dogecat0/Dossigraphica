import json
import os
import logging

logger = logging.getLogger(__name__)

class Geocoder:
    """
    Programmatic geocoder that uses local country data to provide fallback coordinates.
    """
    def __init__(self):
        self.country_map = {}
        self._load_countries()

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

    def get_country_coords(self, country_name: str):
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
