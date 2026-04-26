import pytest
import sqlite3
import tempfile
import os
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from db.domain import Variant, Task, VariantDB, TaskDB, SchedulerStateDB
from db.repsitories import VariantRepository, TaskRepository, SchedulerStateRepository
from webcrowler.crowler import GeneCrawlerService
from webcrowler.schedule import TaskScheduler
from api.api_franklin import FranklinAPIClient
from utils import read_gene_csv, process_input_folder


@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        db_path = tmp.name

    yield db_path

    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def variant_repo(temp_db):
    return VariantRepository()


@pytest.fixture
def task_repo(temp_db):
    return TaskRepository()


@pytest.fixture
def scheduler_state_repo(temp_db):
    return SchedulerStateRepository()


@pytest.fixture
def sample_variant():
    return Variant(
        chr="1",
        pos=12345,
        ref="A",
        alt="G",
        gene="BRCA1",
        db_snp="rs123",
        c_dot="c.123A>G",
        p_dot="p.Lys41Arg",
        transcript="NM_007294",
        classification="Pathogenic",
        score=0.95,
        bayes_score=0.98,
        rules='["rule1", "rule2"]'
    )


@pytest.fixture
def sample_api_response():
    return {
        'location': {
            'chr': '1',
            'pos': 12345,
            'ref': 'A',
            'alt': 'G'
        },
        'gene': 'BRCA1',
        'db_snp': 'rs123',
        'c_dot': 'c.123A>G',
        'p_dot': 'p.Lys41Arg',
        'transcript': 'NM_007294',
        'classification': 'Pathogenic',
        'score': 0.95,
        'bayes_score': 0.98,
        'rules': ['rule1', 'rule2']
    }


@pytest.fixture
def mock_api_client():
    client = Mock(spec=FranklinAPIClient)
    return client


@pytest.fixture
def temp_csv_dir(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return data_dir


@pytest.fixture
def sample_csv_data():
    return [
        {'chrom': '1', 'pos': '12345', 'ref': 'A', 'alt': 'G'},
        {'chrom': '2', 'pos': '67890', 'ref': 'C', 'alt': 'T'},
    ]