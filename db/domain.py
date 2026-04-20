from dataclasses import dataclass, field
from datetime import datetime
import json
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, func
from sqlalchemy.orm import declarative_base
from datetime import datetime


@dataclass
class Variant:
    """Entity: Генетический вариант"""
    chr: str
    pos: int
    ref: str
    alt: str
    gene: str = ""
    db_snp: str = ""
    c_dot: str = ""
    p_dot: str = ""
    transcript: str = ""
    classification: str = ""
    score: float = 0.0
    bayes_score: float = 0.0
    rules: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    @property
    def unique_key(self) -> str:
        return f"{self.chr}-{self.pos}-{self.ref}-{self.alt}"
    
    def update_from_api(self, api_data: dict):
        """Обновить из API response"""
        loc = api_data.get('location', {})
        self.chr = loc.get('chr', self.chr)
        self.pos = loc.get('pos', self.pos)
        self.ref = loc.get('ref', self.ref)
        self.alt = loc.get('alt', self.alt)
        self.gene = api_data.get('gene', self.gene)
        self.db_snp = api_data.get('db_snp', '')
        self.c_dot = api_data.get('c_dot', '')
        self.p_dot = api_data.get('p_dot', '')
        self.transcript = api_data.get('transcript', '')
        self.classification = api_data.get('classification', '')
        self.score = api_data.get('score', 0.0)
        self.bayes_score = api_data.get('bayes_score', 0.0)
        
        rules = api_data.get('rules', [])
        self.rules = json.dumps(rules) if rules else ""
        self.updated_at = datetime.now()
    
    def has_changes(self, other: 'Variant') -> bool:
        """Есть ли изменения для обновления"""
        return (
            self.classification != other.classification or
            abs(self.score - other.score) > 0.001 or
            abs(self.bayes_score - other.bayes_score) > 0.001 or
            self.rules != other.rules
        )
    

@dataclass
class Task:
    """Задача для очереди
    gene(str) - ген
    mode(str) - 'fill', 'update', 'check'
    priority(int) - 1 = высокий, пользовательский, 2 = низкий, по расписанию
    status(str) - pending, processing, done, failed
    created_at(datetime) - время создания
    id 
    """
    gene: str
    mode: str  # 'fill', 'update', 'check'
    priority: int = 2  # 1 = высокий, пользовательский, 2 = низкий, по расписанию
    status: str = "pending"  # pending, processing, done, failed
    created_at: datetime = field(default_factory=datetime.now)
    id: int = None 

Base = declarative_base()

class VariantDB(Base):
    """SQLAlchemy модель"""
    __tablename__ = 'variants'
    
    id = Column(Integer, primary_key=True)
    chr = Column(String(10), nullable=False)
    pos = Column(Integer, nullable=False)
    ref = Column(String(50), nullable=False)
    alt = Column(String(50), nullable=False)
    gene = Column(String(30))
    db_snp = Column(String(30))
    c_dot = Column(String(80))
    p_dot = Column(String(80))
    transcript = Column(String(100))
    classification = Column(String(200))
    score = Column(Float)
    bayes_score = Column(Float)
    rules = Column(Text)
    unique_key = Column(String(200), unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

class TaskDB(Base):
    """Модель задач в БД"""
    __tablename__ = 'tasks'
    
    id = Column(Integer, primary_key=True)
    gene = Column(String(50), nullable=False)
    mode = Column(String(20), nullable=False)
    priority = Column(Integer, default=2)  # 1=high, 2=low
    status = Column(String(20), default="pending")
    created_at = Column(DateTime, default=datetime.now)


class SchedulerStateDB(Base):
    """Состояние планировщика"""
    __tablename__ = 'scheduler_state'
    
    id = Column(Integer, primary_key=True)
    last_run = Column(DateTime)
    next_run = Column(DateTime)