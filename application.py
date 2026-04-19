
"""Application"""
from datetime import datetime, timedelta
import logging
from typing import List, Dict
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
import csv

from api_franklin import FranklinAPIClient
from domain import Task, Variant
from infrastructure import SchedulerStateDB, SchedulerStateRepository, TaskRepository, VariantRepository

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
    
class TaskScheduler:
    """
    Простой планировщик задач.
    
    Что делает:
    1. Добавляет задачи с проверкой на конфликты
    2. Запускает очередь задач последовательно
    3. Проверяет расписание (раз в месяц)
    """
    
    def __init__(self, task_repo: TaskRepository, variant_repo: VariantRepository):
        self.task_repo = task_repo
        self.variant_repo = variant_repo
        self.state_repo = SchedulerStateRepository()
    
    def add_task(self, gene: str, mode: str, is_user_task: bool = True) -> str:
        """
        Добавить задачу с автоматическим разрешением конфликтов.
        
        Правила:
        - Если задача уже есть (pending/processing), то не создаем дубль
        - Если пользователь добавляет задачу, а была фоновая, то повышаем приоритет
        - Если фоновая задача, а пользовательская уже в работе, то пропускаем
        """
        priority = 1 if is_user_task else 2
        
        existing = self.task_repo.find_active_task(gene, mode)
        
        if existing:
            if is_user_task and existing.priority == 2:
                self.task_repo.update_task_priority(existing.id, 1)
                return f"Приоритет задачи {gene}:{mode} повышен до HIGH"
            else:
                return f"Задача {gene}:{mode} уже в работе (статус: {existing.status})"
        
        task = Task(gene=gene, mode=mode, priority=priority)
        task_id = self.task_repo.add_task(task)
        return f"Задача добавлена в очередь (ID: {task_id})"
    
    def run_queue(self, api_client: FranklinAPIClient):
        """
        Выполнить все pending задачи последовательно.
        """
        pending = self.task_repo.get_pending_tasks()
        
        if not pending:
            logger.info("Очередь пуста")
            return
        
        logger.info(f"Запуск очереди: {len(pending)} задач")
        service = GeneCrawlerService(self.variant_repo, api_client)
        
        for task in pending:
            logger.info(f"Выполняется: {task.gene} ({task.mode}) приоритет={task.priority}")
            
            self.task_repo.mark_task_status(task.id, "processing")
            
            try:
                csv_path = f"data/{task.gene}.csv"
                
                if os.path.exists(csv_path):
                    with open(csv_path, 'r', encoding='utf-8') as f:
                        rows = list(csv.DictReader(f, delimiter=';'))
                    service.process_variants(rows, mode=task.mode)
                else:
                    logger.warning(f"CSV координат не найден: {csv_path}")
                
                self.task_repo.mark_task_status(task.id, "done")
                logger.info(f"Задача {task.id} выполнена")
                
            except Exception as e:
                logger.error(f"Ошибка в задаче {task.id}: {e}")
                self.task_repo.mark_task_status(task.id, "failed")
    
    def check_and_run_scheduled(self):
        """
        Проверить, пора ли запустить плановый обход (раз в месяц).
        Если пора, то создать задачи update для всех генов.
        """
        
        engine = create_engine('sqlite:///franklin.db')
        SessionLocal = sessionmaker(bind=engine)
        
        session = SessionLocal()
        try:
            state = session.query(SchedulerStateDB).first()
            now = datetime.now()
            
            if not state or not state.next_run or now >= state.next_run:
                logger.info("Пора запустить плановый обход базы")
                
                genes = self.variant_repo.get_all_genes()
                logger.info(f"Гены для обновления: {genes}")
                
                for gene in genes:
                    self.add_task(gene, "update", is_user_task=False)
                
                if not state:
                    state = SchedulerStateDB()
                    session.add(state)
                
                state.last_run = now
                state.next_run = now + timedelta(days=30)
                session.commit()
                
                logger.info(f"Следующий плановый запуск: {state.next_run}")
                return True
            
            else:
                days_left = (state.next_run - now).days
                logger.info(f"До планового запуска: {days_left} дн.")
                return False
                
        finally:
            session.close()
    
    def setup_schedule(self, start_immediately: bool = False):
        """Установить расписание (раз в месяц)"""

        engine = create_engine('sqlite:///franklin.db')
        SessionLocal = sessionmaker(bind=engine)
        
        session = SessionLocal()
        try:
            state = session.query(SchedulerStateDB).first()
            if not state:
                state = SchedulerStateDB()
                session.add(state)
            
            now = datetime.now()
            if start_immediately:
                state.last_run = now
                state.next_run = now + timedelta(days=30)
            else:
                state.next_run = now + timedelta(days=30)
            
            session.commit()
            logger.info(f"Расписание установлено. Следующий запуск: {state.next_run}")
            
        finally:
            session.close()
