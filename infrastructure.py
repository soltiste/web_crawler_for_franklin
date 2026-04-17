"""Infrastructure"""
import logging
from typing import Optional, List
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime

from domain import Variant

logger = logging.getLogger(__name__)
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


class VariantRepository:
    """работа с БД"""
    
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


