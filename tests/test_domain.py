import pytest
import json
from datetime import datetime
from db.domain import Variant, Task, VariantDB, TaskDB, SchedulerStateDB


class TestVariant:
    def test_variant_creation(self):
        variant = Variant(
            chr="1",
            pos=12345,
            ref="A",
            alt="G",
            gene="BRCA1"
        )
        assert variant.chr == "1"
        assert variant.pos == 12345
        assert variant.ref == "A"
        assert variant.alt == "G"
        assert variant.gene == "BRCA1"

    def test_unique_key(self):
        variant = Variant(chr="1", pos=12345, ref="A", alt="G")
        assert variant.unique_key == "1-12345-A-G"

    def test_update_from_api(self, sample_variant, sample_api_response):
        variant = Variant(chr="", pos=0, ref="", alt="")
        variant.update_from_api(sample_api_response)

        assert variant.chr == "1"
        assert variant.pos == 12345
        assert variant.ref == "A"
        assert variant.alt == "G"
        assert variant.gene == "BRCA1"
        assert variant.classification == "Pathogenic"
        assert variant.score == 0.95
        assert variant.rules == '["rule1", "rule2"]'

    def test_update_from_api_empty_rules(self, sample_api_response):
        variant = Variant(chr="", pos=0, ref="", alt="")
        api_response = sample_api_response.copy()
        api_response['rules'] = []
        variant.update_from_api(api_response)
        assert variant.rules == ""

    def test_has_changes_true(self, sample_variant):
        other = Variant(
            chr="1", pos=12345, ref="A", alt="G",
            classification="Benign"
        )
        assert sample_variant.has_changes(other) is True

    def test_has_changes_false(self, sample_variant):
        other = Variant(
            chr="1", pos=12345, ref="A", alt="G",
            classification="Pathogenic", score=0.95, bayes_score=0.98
        )
        assert sample_variant.has_changes(other) is False

    def test_has_changes_score_difference(self, sample_variant):
        other = Variant(
            chr="1", pos=12345, ref="A", alt="G",
            classification="Pathogenic", score=0.94, bayes_score=0.98
        )
        assert sample_variant.has_changes(other) is True


class TestTask:
    def test_task_creation(self):
        task = Task(gene="BRCA1", mode="fill", priority=1)
        assert task.gene == "BRCA1"
        assert task.mode == "fill"
        assert task.priority == 1
        assert task.status == "pending"
        assert task.id is None

    def test_task_default_priority(self):
        task = Task(gene="BRCA1", mode="update")
        assert task.priority == 2

    def test_task_with_id(self):
        task = Task(gene="BRCA1", mode="check", id=5)
        assert task.id == 5


class TestSQLAlchemyModels:
    def test_variant_db_creation(self):
        variant_db = VariantDB(
            chr="1",
            pos=12345,
            ref="A",
            alt="G",
            unique_key="1-12345-A-G"
        )
        assert variant_db.chr == "1"
        assert variant_db.unique_key == "1-12345-A-G"

    def test_task_db_creation(self):
        task_db = TaskDB(gene="BRCA1", mode="fill")
        assert task_db.gene == "BRCA1"
        assert task_db.status == "pending"

    def test_scheduler_state_db_creation(self):
        state = SchedulerStateDB()
        assert state.id is None
        assert state.last_run is None
        assert state.next_run is None