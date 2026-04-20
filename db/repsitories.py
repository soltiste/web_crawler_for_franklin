"""Infrastructure"""
import logging
from typing import Optional, List
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime
import subprocess
import os

from domain import SchedulerStateDB, Task, TaskDB, Variant, VariantDB

logger = logging.getLogger(__name__)
Base = declarative_base()


class VariantRepository:
    """работа с вариантами в БД"""
    
    def __init__(self, db_path: str = "franklin.db"):
        self.engine = create_engine(f'sqlite:///{db_path}')
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
    
    def _to_domain(self, db_var: VariantDB) -> Variant:
        return Variant(
            chr=db_var.chr, 
            pos=db_var.pos, 
            ref=db_var.ref, 
            alt=db_var.alt,
            gene=db_var.gene, 
            db_snp=db_var.db_snp, 
            c_dot=db_var.c_dot,
            p_dot=db_var.p_dot, 
            transcript=db_var.transcript,
            classification=db_var.classification, 
            score=db_var.score,
            bayes_score=db_var.bayes_score, 
            rules=db_var.rules,
            created_at=db_var.created_at, 
            updated_at=db_var.updated_at
        )
    
    def add_or_update(self, variant: Variant) -> bool:
        session = self.SessionLocal()
        try:
            existing = session.query(VariantDB).filter(
                VariantDB.unique_key == variant.unique_key
            ).first()
            
            if existing:
                if existing.classification != variant.classification:
                    existing.classification = variant.classification
                    existing.score = variant.score
                    existing.bayes_score = variant.bayes_score
                    existing.rules = variant.rules
                    existing.updated_at = datetime.now()
                    session.commit()
                    return True
                return False
            else:
                db_variant = VariantDB(
                    chr=variant.chr, 
                    pos=variant.pos, 
                    ref=variant.ref, 
                    alt=variant.alt,
                    gene=variant.gene, 
                    db_snp=variant.db_snp, 
                    c_dot=variant.c_dot,
                    p_dot=variant.p_dot, 
                    transcript=variant.transcript,
                    classification=variant.classification, 
                    score=variant.score,
                    bayes_score=variant.bayes_score, 
                    rules=variant.rules,
                    unique_key=variant.unique_key
                )
                session.add(db_variant)
                session.commit()
                return True
        finally:
            session.close()
    
    def get_by_gene(self, gene_symbol: str) -> List[Variant]:
        session = self.SessionLocal()
        try:
            variants = session.query(VariantDB).filter(VariantDB.gene == gene_symbol).all()
            return [self._to_domain(v) for v in variants]
        finally:
            session.close()
    
    def get_all(self) -> List[Variant]:
        session = self.SessionLocal()
        try:
            variants = session.query(VariantDB).all()
            return [self._to_domain(v) for v in variants]
        finally:
            session.close()
    
    def find_by_coords(self, chr: str, pos: int, ref: str, alt: str) -> Optional[Variant]:
        session = self.SessionLocal()
        try:
            variant = session.query(VariantDB).filter(
                VariantDB.chr == chr, 
                VariantDB.pos == pos,
                VariantDB.ref == ref, 
                VariantDB.alt == alt
            ).first()
            return self._to_domain(variant) if variant else None
        finally:
            session.close()

    def get_all_genes(self) -> List[str]:
        """Получить список уникальных генов из БД"""
        session = self.SessionLocal()
        try:
            genes = session.query(VariantDB.gene).filter(
                VariantDB.gene.isnot(None),
                VariantDB.gene != ''
            ).distinct().all()
            return [g[0] for g in genes if g[0]]
        finally:
            session.close()

    def validate_c_dot_duplicates(self) -> List[str]:
        """Дубликаты c.dot (разные варианты с одинаковым c.dot - частая ошибка)"""
        session = self.SessionLocal()
        try:
            duplicates = session.query(VariantDB.c_dot).filter(
                VariantDB.c_dot.isnot(None),
                VariantDB.c_dot != ''
            ).group_by(VariantDB.c_dot).having(func.count(VariantDB.id) > 1).all()
            
            return [dup[0] for dup in duplicates]
        finally:
            session.close()
    
    def create_backup(self, backup_dir: str = "backups") -> str:
        """SQL dump для sqlite"""
        os.makedirs(backup_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(backup_dir, f"franklin_backup_{timestamp}.sql")
        
        with open(backup_path, 'w') as f:
            subprocess.run(['sqlite3', 'franklin.db', '.dump'], stdout=f, check=True)
        
        logger.info(f"Backup created: {backup_path}")
        return backup_path
    
class TaskRepository:
    """Работа с задачами"""
    
    def __init__(self, db_path: str = "franklin.db"):
        self.engine = create_engine(f'sqlite:///{db_path}')
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
    
    def find_active_task(self, gene: str, mode: str) -> Optional[Task]:
        """Найти задачу, которая еще не выполнена (pending, processing)"""
        session = self.SessionLocal()
        try:
            db_task = session.query(TaskDB).filter(
                TaskDB.gene == gene,
                TaskDB.mode == mode,
                TaskDB.status.in_(["pending", "processing"])
            ).first()
            
            if db_task:
                return Task(
                    id=db_task.id,
                    gene=db_task.gene,
                    mode=db_task.mode,
                    priority=db_task.priority,
                    status=db_task.status,
                    created_at=db_task.created_at
                )
            return None
        finally:
            session.close()
    
    def add_task(self, task: Task) -> int:
        """Добавить задачу в БД, вернуть ID"""
        session = self.SessionLocal()
        try:
            db_task = TaskDB(
                gene=task.gene,
                mode=task.mode,
                priority=task.priority,
                status=task.status
            )
            session.add(db_task)
            session.commit()
            return db_task.id
        finally:
            session.close()
    
    def update_task_priority(self, task_id: int, new_priority: int):
        """Обновить приоритет задачи"""
        session = self.SessionLocal()
        try:
            session.query(TaskDB).filter(TaskDB.id == task_id).update(
                {"priority": new_priority}
            )
            session.commit()
        finally:
            session.close()
    
    def get_pending_tasks(self) -> List[Task]:
        """Получить все pending задачи с сортировкой по приоритету"""
        session = self.SessionLocal()
        try:
            tasks = session.query(TaskDB).filter(
                TaskDB.status == "pending"
            ).order_by(TaskDB.priority, TaskDB.created_at).all()
            
            return [
                Task(
                    id=t.id,
                    gene=t.gene,
                    mode=t.mode,
                    priority=t.priority,
                    status=t.status,
                    created_at=t.created_at
                )
                for t in tasks
            ]
        finally:
            session.close()
    
    def mark_task_status(self, task_id: int, status: str):
        """Изменить статус задачи"""
        session = self.SessionLocal()
        try:
            session.query(TaskDB).filter(TaskDB.id == task_id).update(
                {"status": status}
            )
            session.commit()
        finally:
            session.close()
    
class SchedulerStateRepository:
    """Cостояние планировщика"""
    
    def __init__(self, db_path: str = "franklin.db"):
        self.engine = create_engine(f'sqlite:///{db_path}')
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
    
    def get_last_run(self) -> Optional[datetime]:
        session = self.SessionLocal()
        try:
            state = session.query(SchedulerStateDB).first()
            return state.last_run if state else None
        finally:
            session.close()
    
    def set_schedule(self, next_run: datetime):
        session = self.SessionLocal()
        try:
            state = session.query(SchedulerStateDB).first()
            if not state:
                state = SchedulerStateDB()
                session.add(state)
            
            state.last_run = datetime.now()
            state.next_run = next_run
            session.commit()
        finally:
            session.close()


