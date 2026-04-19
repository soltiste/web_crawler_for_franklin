"""
Точка входа
"""
import argparse
import csv
import logging
import os
import sys
from datetime import datetime
import sqlite3

from api_franklin import FranklinAPIClient
from infrastructure import VariantRepository, TaskRepository
from application import GeneCrawlerService, TaskScheduler

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


def main():
    parser = argparse.ArgumentParser(
        description='Gene Crawler - сбор данных из Franklin API',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  %(prog)s fill BRCA1 TP53           # Добавить задачи на заполнение
  %(prog)s update BRCA1              # Добавить задачу на обновление  
  %(prog)s check VHL                 # Добавить задачу на проверку
  %(prog)s run                       # Выполнить все задачи из очереди
  %(prog)s schedule                  # Проверить расписание (раз в месяц)
  %(prog)s show --gene BRCA1         # Показать данные из БД
  %(prog)s queue                     # Показать очередь задач
  %(prog)s validate                  # Проверить на дубликаты c.dot
  %(prog)s backup                    # Сделать SQL dump базы
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Режим работы', required=False)
    
    # ========== 2. РЕГИСТРИРУЕМ ВСЕ КОМАНДЫ ==========
    # Пользовательские (кладут задачи в очередь)
    p_fill = subparsers.add_parser('fill', help='Добавить задачу на заполнение БД')
    p_fill.add_argument('genes', nargs='+', help='Гены: BRCA1 TP53')
    
    p_update = subparsers.add_parser('update', help='Добавить задачу на обновление БД')
    p_update.add_argument('genes', nargs='+')

    p_check = subparsers.add_parser('check', help='Добавить задачу на проверку БД')
    p_check.add_argument('genes', nargs='+')
    
    p_run = subparsers.add_parser('run', help='Выполнить все задачи из очереди')

    p_schedule = subparsers.add_parser('schedule', help='Проверить расписание и запустить плановые')
    
    p_show = subparsers.add_parser('show', help='Показать варианты из БД')
    p_show.add_argument('--gene', type=str, help='Фильтр по гену')
    p_show.add_argument('--limit', type=int, default=10)
    
    p_queue = subparsers.add_parser('queue', help='Показать очередь задач')

    p_validate = subparsers.add_parser('validate', help='Проверить дубликаты c.dot')

    p_backup = subparsers.add_parser('backup', help='Сделать SQL dump')
    
    registered = list(subparsers._name_parser_map.keys())
    logger.debug(f"Registered commands: {registered}")
    
    args = parser.parse_args()
    
    try:
        repo = VariantRepository(db_path="franklin.db")
        api = FranklinAPIClient(delay=0.5)
        service = GeneCrawlerService(repo, api)
        task_repo = TaskRepository("franklin.db")
        scheduler = TaskScheduler(task_repo, repo)
    except Exception as e:
        logger.error(f"Ошибка инициализации: {e}")
        sys.exit(1)

    if not args.command:
        parser.print_help()
        return
    
    if args.command == 'show':
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
            print(f"    gene: {row['gene']}, chr:pos: {row['chr']}:{row['pos']}")
            print(f"    {row['ref']}>{row['alt']}, class: {row['classification']}")
            print(f"    c.dot: {row['c_dot'] or '-'}, score: {row['score']}")
        conn.close()
        return
    
    if args.command == 'queue':
        pending = task_repo.get_pending_tasks()
        if not pending:
            print("Очередь пуста")
        else:
            print(f"\nОчередь ({len(pending)}):\n")
            for t in pending:
                prio = "High" if t.priority == 1 else "Low"
                print(f"  [{t.id}] {prio} {t.gene}:{t.mode} ({t.status})")
        return
    
    if args.command == 'validate':
        dups = repo.validate_c_dot_duplicates()
        if dups:
            print(f"Дубликаты c.dot ({len(dups)}): {dups[:5]}{'...' if len(dups)>5 else ''}")
        else:
            print("Дубликатов c.dot нет")
        return
    
    if args.command == 'backup':
        path = repo.create_backup()
        print(f"Бэкап: {path}")
        return
    
    if args.command == 'run':
        logger.info("Запуск очереди...")
        scheduler.run_queue(api)
        logger.info("Готово")
        return
    
    if args.command == 'schedule':
        logger.info("Проверка расписания...")
        ran = scheduler.check_and_run_scheduled()
        print("Плановые задачи добавлены" if ran else "Не время для плановых задач")
        return
    
    if args.command in ['fill', 'update', 'check']:
        logger.info(f"\n{'='*20} {args.command.upper()} {'='*20}")
        results = []
        
        for gene in args.genes:
            if args.command in ['fill', 'update']:
                data = read_gene_csv(gene)
                if not data:
                    logger.warning(f"CSV пуст/не найден для {gene}")
            
            result = scheduler.add_task(gene, args.command, is_user_task=True)
            results.append((gene, result))
            logger.info(f"  {gene}: {result}")
        
        print(f"\nЗадач добавлено: {len(results)}")
        print("Запусти 'python main.py run' для выполнения")
        return
    
    # ----- НЕИЗВЕСТНАЯ КОМАНДА -----
    logger.error(f"Неизвестная команда: {args.command}")
    parser.print_help()


if __name__ == '__main__':
    main()