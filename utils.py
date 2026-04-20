import csv
import os
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"crawler_{datetime.now().strftime('%Y%m%d')}.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

DATA_DIR = "data"

def read_gene_csv(gene_symbol: str) -> list:
    """Читает CSV для конкретного гена"""
    file_path = os.path.join(DATA_DIR, f"{gene_symbol}.csv")
    
    if not os.path.exists(file_path):
        logger.warning(f"CSV not found: {file_path}")
        return []
    
    rows = []
    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            rows.append(row)
            
    logger.info(f"Loaded {len(rows)} rows from {file_path}")
    return rows