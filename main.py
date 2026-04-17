"""Main"""
import argparse
import csv
import logging
import os
from datetime import datetime
import sqlite3

from api_franklin import FranklinAPIClient
from infrastructure import VariantRepository
from application import GeneCrawlerService

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"crawler_{datetime.now().strftime('%Y%m%d')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

DATA_DIR = "data"


def read_gene_csv(gene_symbol: str) -> list:
    """Ищет data/{GENE}.csv, читает CSV для конкретного гена"""
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


def main():
    parser = argparse.ArgumentParser(
        description='Gene Crawler - просто введи названия генов',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
    Examples:
    python main.py fill BRCA1
    python main.py update BRCA1 TP53 VHL
    python main.py check BRCA1
    python main.py show --gene ABC --limit 50
    """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Режим работы')
    
    p_fill = subparsers.add_parser('fill', help='Заполнить БД (создать записи)')
    p_fill.add_argument('genes', nargs='+', help='Названия генов (например, BRCA1 TP53)')
    
    p_update = subparsers.add_parser('update', help='Обновить изменения в БД')
    p_update.add_argument('genes', nargs='+')

    p_check = subparsers.add_parser('check', help='Проверить БД на ошибки')
    p_check.add_argument('genes', nargs='+')

    p_show = subparsers.add_parser('show', help='Показать все поля вариантов')
    p_show.add_argument('--gene', type=str, help='Фильтр по гену')
    p_show.add_argument('--limit', type=int, default=10, help='Макс. записей')
    
    args = parser.parse_args()
    repo = VariantRepository(db_path="franklin.db")
    api = FranklinAPIClient(delay=0.5)
    service = GeneCrawlerService(repo, api)

    if not args.command:
        parser.print_help()
        return
    elif args.command == 'show':
        
        conn = sqlite3.connect("franklin.db")
        conn.row_factory = sqlite3.Row  
        cur = conn.cursor()
        
        query = "SELECT * FROM variants"
        params = []
        if args.gene:
            query += " WHERE gene = ?"
            params.append(args.gene)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(args.limit)
        
        cur.execute(query, params)
        rows = cur.fetchall()
        
        print(f"\n{len(rows)} вариантов\n")
        
        for i, row in enumerate(rows, 1):
            print(f"[{i}] {row['unique_key']}")
            print(f"    gene:           {row['gene']}")
            print(f"    chr:pos:        {row['chr']}:{row['pos']}")
            print(f"    ref>alt:        {row['ref']}>{row['alt']}")
            print(f"    classification: {row['classification']}")
            print(f"    c.dot:          {row['c_dot'] or '-'}")
            print(f"    p.dot:          {row['p_dot'] or '-'}")
            print(f"    transcript:     {row['transcript'] or '-'}")
            print(f"    db_snp:         {row['db_snp'] or '-'}")
            print(f"    score:          {row['score']}")
            print(f"    bayes_score:    {row['bayes_score']}")
            rules = row['rules'] or '-'
            if len(str(rules)) > 100:
                rules = str(rules)[:97] + "..."
            print(f"    rules:          {rules}")
            print(f"    updated:        {row['updated_at']}")
        
        conn.close()
        return
    else:
        for gene in args.genes: 
            logger.info(f"\n{'='*20} {gene} {'='*20}")
            
            data = read_gene_csv(gene)
            if not data:
                logger.warning(f"Skipping {gene} (empty or missing CSV)")
                continue
                
            service.process_variants(data, mode=args.command)
    

    logger.info("\nAll done.")


if __name__ == '__main__':
    main()