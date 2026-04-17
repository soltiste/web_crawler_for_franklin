
"""Application"""
import logging
from typing import List, Dict

from api_franklin import FranklinAPIClient
from domain import Variant
from infrastructure import VariantRepository

logger = logging.getLogger(__name__)


class GeneCrawlerService:
    def __init__(self, repository: VariantRepository, api_client: FranklinAPIClient):
        self.repo = repository
        self.api = api_client

    def process_variants(self, variants_data: List[Dict], mode: str):
        """
        Универсальная функция обработки.
        
        Args:
            variants_data: Список словарей из CSV (ключи: chr, pos, ref, alt).
            mode: 
                - 'fill': Создать запись (или перезаписать).
                - 'update': Обновить, только если классификация изменилась.
                - 'check': Проверить на ошибки (только чтение БД).
        """
        logger.info(f"=== Starting process mode: {mode} ({len(variants_data)} rows) ===")
        
        stats = {"processed": 0, "saved": 0, "updated": 0, "errors": 0, "skipped": 0}

        for i, row in enumerate(variants_data, 1):
            try:
                chr_val = str(row.get('chrom', '')).strip()
                pos_val = int(row.get('pos', 0))
                ref_val = str(row.get('ref', '')).strip().upper()
                alt_val = str(row.get('alt', '')).strip().upper()

                if not all([chr_val, pos_val, ref_val, alt_val]):
                    logger.warning(f"Row {i}: Invalid coordinates, skipping.")
                    continue

                api_response = self.api.classify_by_coords(chr_val, pos_val, ref_val, alt_val)
                
                if not api_response:
                    logger.error(f"Row {i}: API returned empty for {chr_val}-{pos_val}-{ref_val}-{alt_val}")
                    stats["errors"] += 1
                    continue

                current_variant = Variant(chr=chr_val, pos=pos_val, ref=ref_val, alt=alt_val)
                current_variant.update_from_api(api_response)

                if mode == 'fill':
                    success = self.repo.add_or_update(current_variant)
                    
                    if success:
                        stats["saved"] += 1
                        logger.info(f"Row {i}: Saved {current_variant.unique_key} - {current_variant.classification}")
                    else:
                        stats["skipped"] += 1  
                
                elif mode == 'update':
                    db_variant = self.repo.find_by_coords(chr_val, pos_val, ref_val, alt_val)
                    
                    if db_variant and current_variant.has_changes(db_variant):
                        self.repo.update(current_variant)
                        stats["updated"] += 1
                        logger.info(f"Row {i}: Updated classification for {chr_val}-{pos_val}-{ref_val}-{alt_val}")
                    elif not db_variant:
                        stats["skipped"] += 1
                    else:
                        stats["skipped"] += 1 

                elif mode == 'check':
                    db_variant = self.repo.find_by_coords(chr_val, pos_val, ref_val, alt_val)
                    
                    if not db_variant:
                        logger.warning(f"Row {i}: MISSING in DB - {chr_val}-{pos_val}-{ref_val}-{alt_val} ")
                        stats["errors"] += 1
                    elif current_variant.has_changes(db_variant):
                        logger.error(f"Row {i}: MISMATCH - {chr_val}-{pos_val}-{ref_val}-{alt_val}")
                        logger.error(f"   DB: {db_variant.classification}")
                        logger.error(f"   API: {current_variant.classification}")
                        stats["errors"] += 1
                    else:
                        stats["processed"] += 1 

                stats["processed"] += 1

            except Exception as e:
                logger.error(f"Row {i}: Critical error - {e}")
                stats["errors"] += 1

        logger.info(f"=== Finished mode '{mode}'. Stats: {stats} ===")
        return stats