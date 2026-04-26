# tests/test_main.py
import pytest
from unittest.mock import Mock, patch, MagicMock
import sys, time
from main import main, run_daemon


class TestMain:
    @patch('main.VariantRepository')
    @patch('main.FranklinAPIClient')
    @patch('main.GeneCrawlerService')
    @patch('main.TaskRepository')
    @patch('main.TaskScheduler')
    def test_main_no_args(self, mock_scheduler, mock_task_repo, mock_service, mock_api, mock_repo):
        with patch('sys.argv', ['main.py']):
            with patch('argparse.ArgumentParser.print_help') as mock_help:
                main()
                mock_help.assert_called_once()

    @patch('main.VariantRepository')
    @patch('main.FranklinAPIClient')
    @patch('main.GeneCrawlerService')
    @patch('main.TaskRepository')
    @patch('main.TaskScheduler')
    @patch('main.read_gene_csv')
    def test_main_fill_command(self, mock_read_csv, mock_scheduler, mock_task_repo,
                               mock_service, mock_api, mock_repo):
        mock_read_csv.return_value = [{'chrom': '1', 'pos': '12345', 'ref': 'A', 'alt': 'G'}]
        mock_scheduler.return_value.add_task.return_value = "Task added"

        with patch('sys.argv', ['main.py', 'fill', 'BRCA1', 'TP53']):
            with patch('builtins.print') as mock_print:
                main()

                assert mock_scheduler.return_value.add_task.call_count == 2

    @patch('main.sqlite3.connect')
    @patch('main.VariantRepository')
    @patch('main.FranklinAPIClient')
    @patch('main.GeneCrawlerService')
    @patch('main.TaskRepository')
    @patch('main.TaskScheduler')
    def test_main_show_command(self, mock_scheduler, mock_task_repo, mock_service,
                               mock_api, mock_repo, mock_connect):
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            {'unique_key': '1-12345-A-G', 'gene': 'BRCA1', 'chr': '1',
             'pos': 12345, 'ref': 'A', 'alt': 'G', 'classification': 'Pathogenic',
             'c_dot': 'c.123A>G', 'score': 0.95, 'created_at': '2024-01-01'}
        ]
        mock_connect.return_value = mock_conn

        with patch('sys.argv', ['main.py', 'show', '--gene', 'BRCA1']):
            with patch('builtins.print') as mock_print:
                main()

                mock_cursor.execute.assert_called_once()

    @patch('main.VariantRepository')
    @patch('main.FranklinAPIClient')
    @patch('main.GeneCrawlerService')
    @patch('main.TaskRepository')
    @patch('main.TaskScheduler')
    def test_main_queue_command(self, mock_scheduler, mock_task_repo, mock_service,
                                mock_api, mock_repo):
        mock_task_repo.return_value.get_pending_tasks.return_value = [
            Mock(id=1, gene='BRCA1', mode='fill', priority=1, status='pending'),
            Mock(id=2, gene='TP53', mode='update', priority=2, status='pending')
        ]

        with patch('sys.argv', ['main.py', 'queue']):
            with patch('builtins.print') as mock_print:
                main()

                mock_print.assert_any_call("\nОчередь (2):\n")

    @patch('main.VariantRepository')
    @patch('main.FranklinAPIClient')
    @patch('main.GeneCrawlerService')
    @patch('main.TaskRepository')
    @patch('main.TaskScheduler')
    def test_main_validate_command_no_duplicates(self, mock_scheduler, mock_task_repo,
                                                 mock_service, mock_api, mock_repo):
        mock_repo.return_value.validate_c_dot_duplicates.return_value = []

        with patch('sys.argv', ['main.py', 'validate']):
            with patch('builtins.print') as mock_print:
                main()

                mock_print.assert_called_with("Дубликатов c.dot нет")

    @patch('main.VariantRepository')
    @patch('main.FranklinAPIClient')
    @patch('main.GeneCrawlerService')
    @patch('main.TaskRepository')
    @patch('main.TaskScheduler')
    def test_main_backup_command(self, mock_scheduler, mock_task_repo, mock_service,
                                 mock_api, mock_repo):
        mock_repo.return_value.create_backup.return_value = "/backups/backup.sql"

        with patch('sys.argv', ['main.py', 'backup']):
            with patch('builtins.print') as mock_print:
                main()

                mock_print.assert_called_with("Бэкап: /backups/backup.sql")

    @patch('main.VariantRepository')
    @patch('main.FranklinAPIClient')
    @patch('main.GeneCrawlerService')
    @patch('main.TaskRepository')
    @patch('main.TaskScheduler')
    def test_main_run_command(self, mock_scheduler, mock_task_repo, mock_service,
                              mock_api, mock_repo):
        with patch('sys.argv', ['main.py', 'run']):
            with patch('builtins.print') as mock_print:
                main()

                mock_scheduler.return_value.run_queue.assert_called_once()

    @patch('main.VariantRepository')
    @patch('main.FranklinAPIClient')
    @patch('main.GeneCrawlerService')
    @patch('main.TaskRepository')
    @patch('main.TaskScheduler')
    def test_main_schedule_command(self, mock_scheduler, mock_task_repo, mock_service,
                                   mock_api, mock_repo):
        mock_scheduler.return_value.check_and_run_scheduled.return_value = True

        with patch('sys.argv', ['main.py', 'schedule']):
            with patch('builtins.print') as mock_print:
                main()

                mock_print.assert_called_with("Плановые задачи добавлены")

    @patch('main.run_daemon')
    def test_main_daemon_command(self, mock_run_daemon):
        with patch('sys.argv', ['main.py', 'daemon']):
            with patch('builtins.__import__', side_effect=ImportError):
                # Simulate daemon mode
                pass

    @patch('main.process_input_folder')
    @patch('main.TaskScheduler')
    @patch('main.TaskRepository')
    @patch('main.VariantRepository')
    @patch('main.FranklinAPIClient')
    def test_run_daemon(self, mock_api, mock_repo, mock_task_repo,
                        mock_scheduler, mock_process_input):
        mock_scheduler.return_value.run_queue.return_value = True
        mock_scheduler.return_value.check_and_run_scheduled.return_value = False
        mock_process_input.return_value = 0

        with patch('time.sleep') as mock_sleep:
            with patch('main.logger') as mock_logger:
                # Run one iteration then raise KeyboardInterrupt
                def side_effect(*args, **kwargs):
                    raise KeyboardInterrupt()

                mock_sleep.side_effect = side_effect

                try:
                    run_daemon(check_input_every=1, check_schedule_every=86400)
                except KeyboardInterrupt:
                    pass

                assert mock_process_input.called
                assert mock_scheduler.return_value.run_queue.called