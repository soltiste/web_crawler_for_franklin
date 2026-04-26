"""Unit tests for GeneCrawlerService and TaskScheduler classes"""
import pytest
from unittest.mock import Mock, patch, mock_open, call
from datetime import datetime, timedelta
import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from webcrowler.crowler import GeneCrawlerService
from db.domain import Task, Variant
from db.repsitories import SchedulerStateDB


class TestGeneCrawlerService:
    """Test suite for GeneCrawlerService class"""

    @pytest.fixture
    def mock_repository(self):
        """Create mock VariantRepository"""
        return Mock()

    @pytest.fixture
    def mock_api_client(self):
        """Create mock FranklinAPIClient"""
        return Mock()

    @pytest.fixture
    def service(self, mock_repository, mock_api_client):
        """Create GeneCrawlerService instance with mocked dependencies"""
        return GeneCrawlerService(mock_repository, mock_api_client)

    @pytest.fixture
    def sample_variants_data(self):
        """Sample variants data for testing"""
        return [
            {'chrom': '1', 'pos': '12345', 'ref': 'A', 'alt': 'G'},
            {'chrom': '2', 'pos': '67890', 'ref': 'C', 'alt': 'T'},
            {'chrom': '3', 'pos': '11111', 'ref': 'G', 'alt': 'A'}
        ]

    @pytest.fixture
    def sample_api_response(self):
        """Sample API response"""
        return {
            'classification': 'Pathogenic',
            'gene': 'BRCA1',
            'transcript': 'NM_007294.3'
        }

    def test_process_variants_fill_mode_success(self, service, mock_repository,
                                                mock_api_client, sample_variants_data,
                                                sample_api_response):
        """Test process_variants in fill mode with successful processing"""
        # Arrange
        mock_api_client.classify_by_coords.return_value = sample_api_response
        mock_repository.add_or_update.return_value = True

        # Act
        stats = service.process_variants(sample_variants_data, mode='fill')

        # Assert
        assert stats['processed'] == 3  # Each variant counts as processed
        assert stats['saved'] == 3
        assert stats['errors'] == 0
        assert mock_api_client.classify_by_coords.call_count == 3
        assert mock_repository.add_or_update.call_count == 3

    def test_process_variants_update_mode_with_changes(self, service, mock_repository,
                                                       mock_api_client, sample_variants_data,
                                                       sample_api_response):
        """Test process_variants in update mode when classification changed"""
        # Arrange
        mock_api_client.classify_by_coords.return_value = sample_api_response
        mock_db_variant = Mock()
        mock_db_variant.classification = 'Benign'
        mock_repository.find_by_coords.return_value = mock_db_variant

        # Act
        stats = service.process_variants(sample_variants_data, mode='update')

        # Assert
        assert stats['updated'] == 3
        assert mock_repository.update.call_count == 0

    def test_process_variants_update_mode_not_in_db(self, service, mock_repository,
                                                    mock_api_client, sample_variants_data,
                                                    sample_api_response):
        """Test process_variants in update mode when variant not in database"""
        # Arrange
        mock_api_client.classify_by_coords.return_value = sample_api_response
        mock_repository.find_by_coords.return_value = None

        # Act
        stats = service.process_variants(sample_variants_data, mode='update')

        # Assert
        assert stats['skipped'] == 3
        assert mock_repository.update.call_count == 0

    def test_process_variants_check_mode_missing_in_db(self, service, mock_repository,
                                                       mock_api_client, sample_variants_data,
                                                       sample_api_response):
        """Test process_variants in check mode when variant missing in database"""
        # Arrange
        mock_api_client.classify_by_coords.return_value = sample_api_response
        mock_repository.find_by_coords.return_value = None

        # Act
        stats = service.process_variants(sample_variants_data, mode='check')

        # Assert
        assert stats['errors'] == 3
        assert stats['processed'] == 3

    def test_process_variants_check_mode_mismatch(self, service, mock_repository,
                                                  mock_api_client, sample_variants_data,
                                                  sample_api_response):
        """Test process_variants in check mode when classification mismatch"""
        # Arrange
        mock_api_client.classify_by_coords.return_value = sample_api_response
        mock_db_variant = Mock()
        mock_db_variant.classification = 'Benign'
        mock_repository.find_by_coords.return_value = mock_db_variant

        # Act
        stats = service.process_variants(sample_variants_data, mode='check')

        # Assert
        assert stats['errors'] == 3
        assert stats['processed'] == 3

    def test_process_variants_invalid_data(self, service, mock_api_client):
        """Test process_variants with invalid data rows"""
        # Arrange
        invalid_data = [
            {'chrom': '', 'pos': '12345', 'ref': 'A', 'alt': 'G'},
            {'chrom': '1', 'pos': '', 'ref': 'A', 'alt': 'G'},
            {'chrom': '1', 'pos': '12345', 'ref': '', 'alt': 'G'}
        ]

        # Act
        stats = service.process_variants(invalid_data, mode='fill')

        # Assert
        assert mock_api_client.classify_by_coords.call_count == 0
        assert stats['processed'] == 0

    def test_process_variants_api_error(self, service, mock_repository,
                                        mock_api_client, sample_variants_data):
        """Test process_variants when API returns empty response"""
        # Arrange
        mock_api_client.classify_by_coords.return_value = None

        # Act
        stats = service.process_variants(sample_variants_data, mode='fill')

        # Assert
        assert stats['errors'] == 3
        assert mock_repository.add_or_update.call_count == 0

    def test_process_variants_exception_handling(self, service, mock_api_client,
                                                 sample_variants_data):
        """Test process_variants exception handling"""
        # Arrange
        mock_api_client.classify_by_coords.side_effect = Exception("API Error")

        # Act
        stats = service.process_variants(sample_variants_data, mode='fill')

        # Assert
        assert stats['errors'] == 3
        assert stats['processed'] == 0


class TestTaskScheduler:
    """Test suite for TaskScheduler class"""

    @pytest.fixture
    def mock_task_repository(self):
        """Create mock TaskRepository"""
        return Mock()

    @pytest.fixture
    def mock_variant_repository(self):
        """Create mock VariantRepository"""
        return Mock()

    @pytest.fixture
    def mock_api_client(self):
        """Create mock FranklinAPIClient"""
        return Mock()


    def test_add_task_new_task(self, scheduler, mock_task_repository):
        """Test adding a new task"""
        # Arrange
        mock_task_repository.find_active_task.return_value = None
        mock_task_repository.add_task.return_value = "task-123"

        # Act
        result = scheduler.add_task("BRCA1", "update", is_user_task=True)

        # Assert
        assert "Задача добавлена в очередь (ID: task-123)" == result
        mock_task_repository.add_task.assert_called_once()
        added_task = mock_task_repository.add_task.call_args[0][0]
        assert added_task.gene == "BRCA1"
        assert added_task.mode == "update"
        assert added_task.priority == 1

    def test_add_task_duplicate_user_over_background(self, scheduler, mock_task_repository):
        """Test adding user task when background task exists"""
        # Arrange
        existing_task = Mock(id="existing-123", priority=2, status="pending")
        mock_task_repository.find_active_task.return_value = existing_task

        # Act
        result = scheduler.add_task("BRCA1", "update", is_user_task=True)

        # Assert
        assert "Приоритет задачи BRCA1:update повышен до HIGH" == result
        mock_task_repository.update_task_priority.assert_called_once_with("existing-123", 1)
        mock_task_repository.add_task.assert_not_called()

    def test_add_task_background_when_user_exists(self, scheduler, mock_task_repository):
        """Test adding background task when user task exists"""
        # Arrange
        existing_task = Mock(id="existing-123", priority=1, status="processing")
        mock_task_repository.find_active_task.return_value = existing_task

        # Act
        result = scheduler.add_task("BRCA1", "update", is_user_task=False)

        # Assert
        assert "Задача BRCA1:update уже в работе (статус: processing)" == result
        mock_task_repository.update_task_priority.assert_not_called()
        mock_task_repository.add_task.assert_not_called()

    def test_add_task_background_task(self, scheduler, mock_task_repository):
        """Test adding a background task"""
        # Arrange
        mock_task_repository.find_active_task.return_value = None
        mock_task_repository.add_task.return_value = "task-456"

        # Act
        result = scheduler.add_task("TP53", "check", is_user_task=False)

        # Assert
        assert "Задача добавлена в очередь (ID: task-456)" == result
        added_task = mock_task_repository.add_task.call_args[0][0]
        assert added_task.priority == 2

    def test_run_queue_empty(self, scheduler, mock_task_repository, mock_api_client):
        """Test run_queue with no pending tasks"""
        # Arrange
        mock_task_repository.get_pending_tasks.return_value = []

        # Act
        scheduler.run_queue(mock_api_client)

        # Assert
        mock_task_repository.mark_task_status.assert_not_called()

    @patch('application.os.path.exists')
    @patch('builtins.open', new_callable=mock_open, read_data='chrom;pos;ref;alt\n1;12345;A;G\n')
    @patch('application.csv.DictReader')
    @patch('application.GeneCrawlerService')
    def test_run_queue_with_tasks(self, mock_service_class, mock_csv_reader,
                                  mock_file, mock_exists, scheduler,
                                  mock_task_repository, mock_api_client):
        """Test run_queue with pending tasks"""
        # Arrange
        mock_task = Mock(id="task-1", gene="BRCA1", mode="update", priority=1)
        mock_task_repository.get_pending_tasks.return_value = [mock_task]
        mock_exists.return_value = True

        mock_service_instance = Mock()
        mock_service_class.return_value = mock_service_instance

        mock_csv_reader.return_value = [{'chrom': '1', 'pos': '12345', 'ref': 'A', 'alt': 'G'}]

        # Act
        scheduler.run_queue(mock_api_client)

        # Assert
        mock_task_repository.mark_task_status.assert_any_call("task-1", "processing")
        mock_task_repository.mark_task_status.assert_any_call("task-1", "done")
        mock_service_instance.process_variants.assert_called_once()

    @patch('application.os.path.exists')
    def test_run_queue_missing_csv(self, mock_exists, scheduler, mock_task_repository,
                                   mock_api_client):
        """Test run_queue when CSV file is missing"""
        # Arrange
        mock_task = Mock(id="task-1", gene="BRCA1", mode="update", priority=1)
        mock_task_repository.get_pending_tasks.return_value = [mock_task]
        mock_exists.return_value = False

        # Act
        scheduler.run_queue(mock_api_client)

        # Assert
        mock_task_repository.mark_task_status.assert_any_call("task-1", "processing")
        mock_task_repository.mark_task_status.assert_any_call("task-1", "done")

    def test_run_queue_task_exception(self, scheduler, mock_task_repository,
                                      mock_api_client):
        """Test run_queue when task raises an exception"""
        # Arrange
        mock_task = Mock(id="task-1", gene="BRCA1", mode="update", priority=1)
        mock_task_repository.get_pending_tasks.return_value = [mock_task]

        with patch('application.os.path.exists') as mock_exists:
            mock_exists.side_effect = Exception("File system error")

            # Act
            scheduler.run_queue(mock_api_client)

            # Assert
            mock_task_repository.mark_task_status.assert_any_call("task-1", "failed")

    @patch('application.create_engine')
    @patch('application.sessionmaker')
    def test_check_and_run_scheduled_first_run(self, mock_sessionmaker, mock_create_engine,
                                               scheduler, mock_task_repository,
                                               mock_variant_repository):
        """Test check_and_run_scheduled when no state exists"""
        # Arrange
        mock_session = Mock()
        mock_sessionmaker.return_value = mock_session
        mock_session.query.return_value.first.return_value = None

        mock_variant_repository.get_all_genes.return_value = ["BRCA1", "TP53"]
        mock_task_repository.add_task.return_value = "task-id"

        # Act
        result = scheduler.check_and_run_scheduled()

        # Assert
        assert result is True
        assert mock_task_repository.add_task.call_count == 2
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    @patch('application.create_engine')
    @patch('application.sessionmaker')
    def test_check_and_run_scheduled_due(self, mock_sessionmaker, mock_create_engine,
                                         scheduler, mock_task_repository,
                                         mock_variant_repository):
        """Test check_and_run_scheduled when scheduled run is due"""
        # Arrange
        mock_session = Mock()
        mock_sessionmaker.return_value = mock_session

        past_date = datetime.now() - timedelta(days=1)
        mock_state = Mock(last_run=past_date, next_run=past_date)
        mock_session.query.return_value.first.return_value = mock_state

        mock_variant_repository.get_all_genes.return_value = ["BRCA1"]

        # Act
        result = scheduler.check_and_run_scheduled()

        # Assert
        assert result is True
        assert mock_task_repository.add_task.call_count == 1

    @patch('application.create_engine')
    @patch('application.sessionmaker')
    def test_check_and_run_scheduled_not_due(self, mock_sessionmaker, mock_create_engine,
                                             scheduler, mock_task_repository):
        """Test check_and_run_scheduled when scheduled run is not due yet"""
        # Arrange
        mock_session = Mock()
        mock_sessionmaker.return_value = mock_session

        future_date = datetime.now() + timedelta(days=15)
        mock_state = Mock(last_run=datetime.now(), next_run=future_date)
        mock_session.query.return_value.first.return_value = mock_state

        # Act
        result = scheduler.check_and_run_scheduled()

        # Assert
        assert result is False
        mock_task_repository.add_task.assert_not_called()

    @patch('application.create_engine')
    @patch('application.sessionmaker')
    def test_setup_schedule_new_state(self, mock_sessionmaker, mock_create_engine,
                                      scheduler):
        """Test setup_schedule when no state exists"""
        # Arrange
        mock_session = Mock()
        mock_sessionmaker.return_value = mock_session
        mock_session.query.return_value.first.return_value = None

        # Act
        scheduler.setup_schedule(start_immediately=False)

        # Assert
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    @patch('application.create_engine')
    @patch('application.sessionmaker')
    def test_setup_schedule_existing_state(self, mock_sessionmaker, mock_create_engine,
                                           scheduler):
        """Test setup_schedule with existing state"""
        # Arrange
        mock_session = Mock()
        mock_sessionmaker.return_value = mock_session
        mock_state = Mock()
        mock_session.query.return_value.first.return_value = mock_state

        # Act
        scheduler.setup_schedule(start_immediately=True)

        # Assert
        mock_session.add.assert_not_called()
        mock_session.commit.assert_called_once()

    @patch('application.create_engine')
    @patch('application.sessionmaker')
    def test_setup_schedule_start_immediately(self, mock_sessionmaker, mock_create_engine,
                                              scheduler):
        """Test setup_schedule with start_immediately=True"""
        # Arrange
        mock_session = Mock()
        mock_sessionmaker.return_value = mock_session
        mock_state = Mock()
        mock_session.query.return_value.first.return_value = mock_state

        # Act
        scheduler.setup_schedule(start_immediately=True)

        # Assert
        assert mock_state.last_run is not None
        assert mock_state.next_run is not None

    @patch('application.create_engine')
    @patch('application.sessionmaker')
    def test_check_and_run_scheduled_exception_handling(self, mock_sessionmaker,
                                                        mock_create_engine,
                                                        scheduler):
        """Test check_and_run_scheduled exception handling"""
        # Arrange
        mock_session = Mock()
        mock_sessionmaker.return_value = mock_session
        mock_session.query.side_effect = Exception("Database error")

        # Act & Assert
        with pytest.raises(Exception, match="Database error"):
            scheduler.check_and_run_scheduled()
        mock_session.close.assert_called_once()


