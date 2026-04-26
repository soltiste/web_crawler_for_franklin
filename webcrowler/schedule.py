from datetime import datetime, timedelta
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
import csv

from api.api_franklin import FranklinAPIClient
from db.domain import Task, TaskDB
from db.repsitories import SchedulerStateDB, SchedulerStateRepository, TaskRepository, VariantRepository
from webcrowler.crowler import GeneCrawlerService

logger = logging.getLogger(__name__)

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
    
    def run_queue(self, api_client: FranklinAPIClient, max_task_minutes: int = 600):
        """
        Выполнить одну задачу с очереди
        
        Args:
            max_task_minutes: Если задача висит в processing дольше — сбросить
        """
        
        session = self.task_repo.SessionLocal()
        try:
            now = datetime.now()
            timeout_threshold = now - timedelta(minutes=max_task_minutes)

            count_failed = session.query(TaskDB).filter(
                TaskDB.status == 'processing',
                TaskDB.created_at < timeout_threshold 
            ).update({"status": "failed"})

            count_pending = session.query(TaskDB).filter(
                TaskDB.status == 'processing',
                TaskDB.created_at >= timeout_threshold 
            ).update({"status": "pending"})

            session.commit()

            if count_failed > 0:
                logger.warning(f"Помечено как FAILED: {count_failed} задач")
            if count_pending > 0:
                logger.info(f"Восстановлено в PENDING: {count_pending} задач")

        finally:
            session.close()

        pending = self.task_repo.get_pending_tasks()
        if not pending:
            return None 
        
        task = pending[0]
        logger.info(f"Задача: {task.gene} ({task.mode}), приоритет={task.priority}")
        
        self.task_repo.mark_task_status(task.id, "processing")
        service = GeneCrawlerService(self.variant_repo, api_client)
        
        try:
            csv_path = f"datamap/{task.gene}.csv"
            if os.path.exists(csv_path):
                with open(csv_path, 'r', encoding='utf-8') as f:
                    rows = list(csv.DictReader(f, delimiter=';'))
                service.process_variants(rows, mode=task.mode)
                self.task_repo.mark_task_status(task.id, "done")
                logger.info(f"Задача {task.id} выполнена")
            else:
                logger.warning(f"CSV не найден: {csv_path}")
                self.task_repo.mark_task_status(task.id, "failed") 
            
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка в задаче {task.id}: {e}")
            self.task_repo.mark_task_status(task.id, "failed")
            return False
    
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

                try:
                    backup_path = self.variant_repo.create_backup()
                    logger.info(f"Плановый бэкап: {backup_path}")
                except Exception as e:
                    logger.error(f"Ошибка при создании бэкапа: {e}")
                
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
