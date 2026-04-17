import logging
import requests
import time
logger = logging.getLogger(__name__)
from typing import List, Optional

class FranklinAPIClient:
    
    BASE_URL = "https://franklin.genoox.com/api"
    
    def __init__(self, timeout: int = 10, delay: float = 0.5):
        self.timeout = timeout
        self.delay = delay
        self._session = None
    
    @property
    def session(self):
        if self._session is None:
            self._session = requests.Session()
        return self._session
    
    def parse_search(self, search_text: str, reference_version: str = "hg38") -> List[dict]:
        """
        Поиск вариантов по тексту (gene:c.dot, rsID)
        """
        
        url = f"{self.BASE_URL}/parse_search"
        data = {
            "search_text_input": search_text,
            "case_context": {
                "phenotypes": [],
                "ethnicity": [],
                "consanguinity": None,
                "family_inheritance_status": None,
                "reported_classification": None,
                "sex": None,
                "search_term": search_text
            },
            "roh_allowed": True,
            "reference_version": reference_version
        }
        
        try:
            logger.info(f"Searching: {search_text}")
            response = self.session.post(url, json=data, timeout=self.timeout)
            
            if response.status_code == 200:
                result = response.json()
                time.sleep(self.delay)
                variants = result.get('snp_variants', [])
                logger.info(f"Found {len(variants)} variant(s)")
                return variants
            else:
                logger.error(f"API error {response.status_code}: {response.text[:500]}")
                return []
                
        except requests.RequestException as e:
            logger.error(f"Request failed: {e}")
            return []
        except ValueError as e:
            # Если ответ не JSON
            logger.error(f"Failed to parse JSON response: {e}, raw: {response.text[:200]}")
            return []
        
    def classify_by_coords(self, chr: str, pos: int, ref: str, alt: str) -> Optional[dict]:
        """Классификация варианта по координатам"""
        
        url = f"{self.BASE_URL}/classify"
        data = {
            "variant": {
                "chrom": chr,
                "pos": int(pos),
                "ref": ref,
                "alt": alt,
                "reference_version": "hg38"
            },
            "is_versioned_request": False,
        }
        
        try:
            logger.info(f"Classifying {chr}-{pos}-{ref}-{alt}")
            response = self.session.post(url, json=data, timeout=self.timeout)
            
            if response.status_code == 200:
                result = response.json()
                time.sleep(self.delay)
                return result
            else:
                logger.error(f"API error: {response.status_code}")
                return None
                
        except requests.RequestException as e:
            logger.error(f"Request failed: {e}")
            return None
        