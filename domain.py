"""Domain"""
from dataclasses import dataclass, field
from datetime import datetime
import json


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