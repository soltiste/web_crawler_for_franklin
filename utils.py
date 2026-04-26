import csv
import os
import logging
import re
from datetime import datetime
import shutil

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


def process_input_folder(input_dir: str = "input", processed_dir: str = "processed",
                         max_age_minutes: int = 3, scheduler=None) -> int:
    """
    Сканирует input/, обрабатывает свежие файлы, старые просто переносит
    """
    os.makedirs(processed_dir, exist_ok=True)
    tasks_added = 0
    now = datetime.now()

    for filename in os.listdir(input_dir):
        if not filename.endswith('.txt'):
            continue

        filepath = os.path.join(input_dir, filename)

        match = re.search(r'(\d{8}_\d{6})\.txt$', filename)
        if not match:
            logger.warning(f"Пропущен файл (неверный формат имени): {filename}")
            continue

        try:
            file_time = datetime.strptime(match.group(1), "%Y%m%d_%H%M%S")
            age_sec = abs((now - file_time).total_seconds())
            is_fresh = age_sec <= max_age_minutes * 60

            if not is_fresh:
                logger.info(f"{filename} старше {max_age_minutes} мин. Команды пропущены.")
            else:
                with open(filepath, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        parts = line.split()
                        if len(parts) < 2:
                            continue

                        command, *genes = parts
                        mode = command.lower()
                        if mode in ['fill', 'update', 'check']:
                            for gene in genes:
                                result = scheduler.add_task(gene, mode, is_user_task=True)
                                logger.info(f"{filename}: {result}")
                                tasks_added += 1

            dest = os.path.join(processed_dir, filename)
            shutil.move(filepath, dest)
            logger.info(f"Файл перемещён: {filename} → {processed_dir}/")

        except Exception as e:
            logger.error(f"Ошибка при обработке {filename}: {e}")

    return tasks_added