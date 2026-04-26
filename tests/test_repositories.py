# tests/test_repositories.py
import pytest
from datetime import datetime, timedelta
from db.domain import Variant, Task
from db.repsitories import VariantRepository, TaskRepository, SchedulerStateRepository


class TestVariantRepository:
    def test_add_new_variant(self, variant_repo, sample_variant):
        result = variant_repo.add_or_update(sample_variant)
        assert result is True

        saved = variant_repo.find_by_coords("1", 12345, "A", "G")
        assert saved is not None
        assert saved.gene == "BRCA1"

    def test_update_existing_variant(self, variant_repo, sample_variant):
        variant_repo.add_or_update(sample_variant)

        updated_variant = Variant(
            chr="1", pos=12345, ref="A", alt="G",
            classification="Benign", score=0.5
        )
        result = variant_repo.add_or_update(updated_variant)
        assert result is True

        saved = variant_repo.find_by_coords("1", 12345, "A", "G")
        assert saved.classification == "Benign"

    def test_add_duplicate_no_changes(self, variant_repo, sample_variant):
        variant_repo.add_or_update(sample_variant)
        result = variant_repo.add_or_update(sample_variant)
        assert result is False

    def test_get_by_gene(self, variant_repo, sample_variant):
        variant_repo.add_or_update(sample_variant)

        variant2 = Variant(
            chr="2", pos=67890, ref="C", alt="T",
            gene="BRCA1"
        )
        variant_repo.add_or_update(variant2)

        variants = variant_repo.get_by_gene("BRCA1")
        assert len(variants) == 2

    def test_get_all(self, variant_repo, sample_variant):
        variant_repo.add_or_update(sample_variant)

        variant2 = Variant(
            chr="2", pos=67890, ref="C", alt="T",
            gene="TP53"
        )
        variant_repo.add_or_update(variant2)

        variants = variant_repo.get_all()
        assert len(variants) == 2

    def test_find_by_coords_not_found(self, variant_repo):
        result = variant_repo.find_by_coords("1", 99999, "A", "G")
        assert result is None

    def test_get_all_genes(self, variant_repo, sample_variant):
        variant_repo.add_or_update(sample_variant)

        variant2 = Variant(
            chr="2", pos=67890, ref="C", alt="T",
            gene="TP53"
        )
        variant_repo.add_or_update(variant2)

        genes = variant_repo.get_all_genes()
        assert set(genes) == {"BRCA1", "TP53"}

    def test_get_all_genes_empty(self, variant_repo):
        genes = variant_repo.get_all_genes()
        assert genes == []

    def test_validate_c_dot_duplicates(self, variant_repo):
        variant1 = Variant(
            chr="1", pos=12345, ref="A", alt="G",
            c_dot="c.123A>G", gene="BRCA1"
        )
        variant2 = Variant(
            chr="1", pos=67890, ref="C", alt="T",
            c_dot="c.123A>G", gene="BRCA1"
        )
        variant_repo.add_or_update(variant1)
        variant_repo.add_or_update(variant2)

        duplicates = variant_repo.validate_c_dot_duplicates()
        assert "c.123A>G" in duplicates

    def test_create_backup(self, variant_repo, sample_variant, tmp_path):
        variant_repo.add_or_update(sample_variant)

        with patch('os.makedirs') as mock_makedirs:
            with patch('subprocess.run') as mock_run:
                backup_path = variant_repo.create_backup(backup_dir=str(tmp_path))
                assert mock_run.called


class TestTaskRepository:
    def test_add_task(self, task_repo):
        task = Task(gene="BRCA1", mode="fill", priority=1)
        task_id = task_repo.add_task(task)
        assert task_id is not None

    def test_find_active_task_pending(self, task_repo):
        task = Task(gene="BRCA1", mode="fill", priority=1)
        task_id = task_repo.add_task(task)

        found = task_repo.find_active_task("BRCA1", "fill")
        assert found is not None
        assert found.gene == "BRCA1"
        assert found.mode == "fill"
        assert found.status == "pending"

    def test_find_active_task_processing(self, task_repo):
        task = Task(gene="BRCA1", mode="fill", priority=1)
        task_id = task_repo.add_task(task)
        task_repo.mark_task_status(task_id, "processing")

        found = task_repo.find_active_task("BRCA1", "fill")
        assert found is not None
        assert found.status == "processing"

    def test_find_active_task_done(self, task_repo):
        task = Task(gene="BRCA1", mode="fill", priority=1)
        task_id = task_repo.add_task(task)
        task_repo.mark_task_status(task_id, "done")

        found = task_repo.find_active_task("BRCA1", "fill")
        assert found is None

    def test_find_active_task_not_exists(self, task_repo):
        found = task_repo.find_active_task("BRCA1", "fill")
        assert found is None

    def test_update_task_priority(self, task_repo):
        task = Task(gene="BRCA1", mode="fill", priority=2)
        task_id = task_repo.add_task(task)

        task_repo.update_task_priority(task_id, 1)

        found = task_repo.find_active_task("BRCA1", "fill")
        assert found.priority == 1

    def test_get_pending_tasks_order(self, task_repo):
        task1 = Task(gene="BRCA1", mode="fill", priority=1)
        task2 = Task(gene="TP53", mode="update", priority=2)
        task3 = Task(gene="VHL", mode="check", priority=1)

        task_repo.add_task(task1)
        task_repo.add_task(task2)
        task_repo.add_task(task3)

        pending = task_repo.get_pending_tasks()
        assert len(pending) == 3
        assert pending[0].priority == 1
        assert pending[1].priority == 1
        assert pending[2].priority == 2

    def test_mark_task_status(self, task_repo):
        task = Task(gene="BRCA1", mode="fill")
        task_id = task_repo.add_task(task)

        task_repo.mark_task_status(task_id, "processing")
        found = task_repo.find_active_task("BRCA1", "fill")
        assert found.status == "processing"

        task_repo.mark_task_status(task_id, "done")
        found = task_repo.find_active_task("BRCA1", "fill")
        assert found is None


class TestSchedulerStateRepository:
    def test_get_last_run_none(self, scheduler_state_repo):
        last_run = scheduler_state_repo.get_last_run()
        assert last_run is None

    def test_set_schedule(self, scheduler_state_repo):
        next_run = datetime.now() + timedelta(days=30)
        scheduler_state_repo.set_schedule(next_run)

        last_run = scheduler_state_repo.get_last_run()
        assert last_run is not None