# tests/test_schedule.py
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from webcrowler.schedule import TaskScheduler
from db.domain import Task


class TestTaskScheduler:
    def test_add_task_new_user_task(self, task_repo, variant_repo):
        scheduler = TaskScheduler(task_repo, variant_repo)

        result = scheduler.add_task("BRCA1", "fill", is_user_task=True)

        assert "добавлена" in result
        tasks = task_repo.get_pending_tasks()
        assert len(tasks) == 1
        assert tasks[0].priority == 1

    def test_add_task_new_background_task(self, task_repo, variant_repo):
        scheduler = TaskScheduler(task_repo, variant_repo)

        result = scheduler.add_task("BRCA1", "fill", is_user_task=False)

        assert "добавлена" in result
        tasks = task_repo.get_pending_tasks()
        assert len(tasks) == 1
        assert tasks[0].priority == 2

    def test_add_task_duplicate_skip(self, task_repo, variant_repo):
        scheduler = TaskScheduler(task_repo, variant_repo)

        scheduler.add_task("BRCA1", "fill", is_user_task=True)
        result = scheduler.add_task("BRCA1", "fill", is_user_task=True)

        assert "уже в работе" in result
        tasks = task_repo.get_pending_tasks()
        assert len(tasks) == 1

    def test_add_task_priority_upgrade(self, task_repo, variant_repo):
        scheduler = TaskScheduler(task_repo, variant_repo)

        # Add background task first
        scheduler.add_task("BRCA1", "fill", is_user_task=False)

        # User adds same task - should upgrade priority
        result = scheduler.add_task("BRCA1", "fill", is_user_task=True)

        assert "повышен" in result
        tasks = task_repo.get_pending_tasks()
        assert tasks[0].priority == 1

    def test_run_queue_no_pending_tasks(self, task_repo, variant_repo, mock_api_client):
        scheduler = TaskScheduler(task_repo, variant_repo)

        result = scheduler.run_queue(mock_api_client)

        assert result is None

    @patch('webcrowler.schedule.csv.DictReader')
    def test_run_queue_success(self, mock_dict_reader, task_repo, variant_repo, mock_api_client, sample_csv_data):
        scheduler = TaskScheduler(task_repo, variant_repo)
        scheduler.add_task("BRCA1", "fill", is_user_task=True)

        mock_dict_reader.return_value = sample_csv_data

        with patch('webcrowler.schedule.os.path.exists', return_value=True):
            with patch('builtins.open', MagicMock()):
                result = scheduler.run_queue(mock_api_client)

        assert result is True

        pending = task_repo.get_pending_tasks()
        assert len(pending) == 0

    @patch('webcrowler.schedule.os.path.exists', return_value=False)
    def test_run_queue_csv_not_found(self, mock_exists, task_repo, variant_repo, mock_api_client):
        scheduler = TaskScheduler(task_repo, variant_repo)
        scheduler.add_task("BRCA1", "fill", is_user_task=True)

        result = scheduler.run_queue(mock_api_client)

        assert result is False

        task = task_repo.find_active_task("BRCA1", "fill")
        assert task is None  # Task should be marked failed

    def test_run_queue_processing_timeout(self, task_repo, variant_repo, mock_api_client):
        scheduler = TaskScheduler(task_repo, variant_repo)

        # Add task and mark as processing with old timestamp
        task_id = task_repo.add_task(Task(gene="BRCA1", mode="fill"))

        with patch('webcrowler.schedule.datetime') as mock_datetime:
            old_time = datetime.now() - timedelta(minutes=700)
            mock_datetime.now.return_value = old_time
            task_repo.mark_task_status(task_id, "processing")

            # Run queue should reset stuck tasks
            scheduler.run_queue(mock_api_client)

            # Check task was marked as failed
            session = task_repo.SessionLocal()
            from db.domain import TaskDB
            task_db = session.query(TaskDB).filter(TaskDB.id == task_id).first()
            session.close()

            # Task should be marked as failed after timeout
            assert task_db.status == "failed" or task_db.status == "pending"

    def test_check_and_run_scheduled_first_time(self, task_repo, variant_repo):
        scheduler = TaskScheduler(task_repo, variant_repo)

        with patch.object(variant_repo, 'get_all_genes', return_value=['BRCA1', 'TP53']):
            with patch.object(variant_repo, 'create_backup', return_value='/backup/path'):
                result = scheduler.check_and_run_scheduled()

        assert result is True

        # Should have added tasks for both genes
        pending = task_repo.get_pending_tasks()
        assert len(pending) == 2

    def test_check_and_run_scheduled_not_time_yet(self, task_repo, variant_repo):
        scheduler = TaskScheduler(task_repo, variant_repo)

        # Setup state with future next_run
        session = task_repo.SessionLocal()
        from db.domain import SchedulerStateDB
        state = SchedulerStateDB()
        state.last_run = datetime.now()
        state.next_run = datetime.now() + timedelta(days=15)
        session.add(state)
        session.commit()
        session.close()

        with patch.object(variant_repo, 'get_all_genes', return_value=[]):
            result = scheduler.check_and_run_scheduled()

        assert result is False

    def test_setup_schedule_new(self, task_repo, variant_repo):
        scheduler = TaskScheduler(task_repo, variant_repo)

        scheduler.setup_schedule(start_immediately=False)

        session = task_repo.SessionLocal()
        from db.domain import SchedulerStateDB
        state = session.query(SchedulerStateDB).first()
        session.close()

        assert state is not None
        assert state.next_run is not None

    def test_setup_schedule_start_immediately(self, task_repo, variant_repo):
        scheduler = TaskScheduler(task_repo, variant_repo)

        scheduler.setup_schedule(start_immediately=True)

        session = task_repo.SessionLocal()
        from db.domain import SchedulerStateDB
        state = session.query(SchedulerStateDB).first()
        session.close()

        assert state is not None
        assert state.last_run is not None