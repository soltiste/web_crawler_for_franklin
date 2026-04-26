# tests/test_utils.py
import pytest
import os
import csv
import tempfile
import shutil
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from utils import read_gene_csv, process_input_folder


class TestReadGeneCSV:
    def test_read_existing_csv(self, temp_csv_dir, sample_csv_data):
        # Create CSV file
        csv_path = temp_csv_dir / "BRCA1.csv"
        with open(csv_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['chrom', 'pos', 'ref', 'alt'], delimiter=';')
            writer.writeheader()
            writer.writerows(sample_csv_data)

        with patch('utils.DATA_DIR', str(temp_csv_dir)):
            rows = read_gene_csv("BRCA1")

        assert len(rows) == 2
        assert rows[0]['chrom'] == '1'

    def test_read_nonexistent_csv(self, temp_csv_dir):
        with patch('utils.DATA_DIR', str(temp_csv_dir)):
            rows = read_gene_csv("NONEXISTENT")

        assert rows == []

    def test_read_empty_csv(self, temp_csv_dir):
        csv_path = temp_csv_dir / "EMPTY.csv"
        with open(csv_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['chrom', 'pos', 'ref', 'alt'], delimiter=';')
            writer.writeheader()

        with patch('utils.DATA_DIR', str(temp_csv_dir)):
            rows = read_gene_csv("EMPTY")

        assert len(rows) == 0


class TestProcessInputFolder:
    @pytest.fixture
    def input_dir_setup(self, tmp_path):
        input_dir = tmp_path / "input"
        processed_dir = tmp_path / "processed"
        input_dir.mkdir()
        return input_dir, processed_dir

    def create_test_file(self, input_dir, filename, content):
        filepath = input_dir / filename
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return filepath

    def test_process_fresh_file(self, input_dir_setup):
        input_dir, processed_dir = input_dir_setup
        scheduler = Mock()

        # Create fresh file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"commands_{timestamp}.txt"
        content = "fill BRCA1 TP53\nupdate VHL"

        self.create_test_file(input_dir, filename, content)

        tasks_added = process_input_folder(
            input_dir=str(input_dir),
            processed_dir=str(processed_dir),
            max_age_minutes=3,
            scheduler=scheduler
        )

        assert tasks_added == 3  # fill BRCA1, fill TP53, update VHL
        assert scheduler.add_task.call_count == 3

        # File should be moved to processed
        assert not (input_dir / filename).exists()
        assert (processed_dir / filename).exists()

    def test_process_old_file(self, input_dir_setup):
        input_dir, processed_dir = input_dir_setup
        scheduler = Mock()

        # Create old file
        old_time = datetime.now() - timedelta(minutes=10)
        timestamp = old_time.strftime("%Y%m%d_%H%M%S")
        filename = f"commands_{timestamp}.txt"
        content = "fill BRCA1"

        self.create_test_file(input_dir, filename, content)

        tasks_added = process_input_folder(
            input_dir=str(input_dir),
            processed_dir=str(processed_dir),
            max_age_minutes=3,
            scheduler=scheduler
        )

        assert tasks_added == 0  # No tasks added for old file
        assert scheduler.add_task.call_count == 0

        # File should still be moved to processed
        assert (processed_dir / filename).exists()

    def test_invalid_filename_format(self, input_dir_setup):
        input_dir, processed_dir = input_dir_setup
        scheduler = Mock()

        filename = "invalid_name.txt"
        content = "fill BRCA1"

        self.create_test_file(input_dir, filename, content)

        tasks_added = process_input_folder(
            input_dir=str(input_dir),
            processed_dir=str(processed_dir),
            scheduler=scheduler
        )

        assert tasks_added == 0
        assert (processed_dir / filename).exists()

    def test_skip_non_txt_files(self, input_dir_setup):
        input_dir, processed_dir = input_dir_setup
        scheduler = Mock()

        filename = "commands_log.csv"
        filepath = input_dir / filename
        with open(filepath, 'w') as f:
            f.write("data")

        tasks_added = process_input_folder(
            input_dir=str(input_dir),
            processed_dir=str(processed_dir),
            scheduler=scheduler
        )

        assert tasks_added == 0
        assert (input_dir / filename).exists()  # Not moved
        assert not (processed_dir / filename).exists()

    def test_empty_file(self, input_dir_setup):
        input_dir, processed_dir = input_dir_setup
        scheduler = Mock()

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"commands_{timestamp}.txt"
        content = ""

        self.create_test_file(input_dir, filename, content)

        tasks_added = process_input_folder(
            input_dir=str(input_dir),
            processed_dir=str(processed_dir),
            scheduler=scheduler
        )

        assert tasks_added == 0

    def test_commented_lines(self, input_dir_setup):
        input_dir, processed_dir = input_dir_setup
        scheduler = Mock()

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"commands_{timestamp}.txt"
        content = "# This is a comment\nfill BRCA1\n# Another comment\nupdate TP53"

        self.create_test_file(input_dir, filename, content)

        tasks_added = process_input_folder(
            input_dir=str(input_dir),
            processed_dir=str(processed_dir),
            scheduler=scheduler
        )

        assert tasks_added == 2

    def test_malformed_lines(self, input_dir_setup):
        input_dir, processed_dir = input_dir_setup
        scheduler = Mock()

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"commands_{timestamp}.txt"
        content = "fill\nupdate BRCA1 TP53\ninvalid command"

        self.create_test_file(input_dir, filename, content)

        tasks_added = process_input_folder(
            input_dir=str(input_dir),
            processed_dir=str(processed_dir),
            scheduler=scheduler
        )

        # Only "update BRCA1 TP53" should be processed
        assert tasks_added == 2

    def test_multiple_commands_per_line(self, input_dir_setup):
        input_dir, processed_dir = input_dir_setup
        scheduler = Mock()

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"commands_{timestamp}.txt"
        content = "fill BRCA1 TP53 VHL\nupdate BRCA1"

        self.create_test_file(input_dir, filename, content)

        tasks_added = process_input_folder(
            input_dir=str(input_dir),
            processed_dir=str(processed_dir),
            scheduler=scheduler
        )

        assert tasks_added == 4  # fill BRCA1, fill TP53, fill VHL, update BRCA1

    def test_case_insensitive_commands(self, input_dir_setup):
        input_dir, processed_dir = input_dir_setup
        scheduler = Mock()

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"commands_{timestamp}.txt"
        content = "FILL BRCA1\nUPDATE TP53\nCHECK VHL"

        self.create_test_file(input_dir, filename, content)

        tasks_added = process_input_folder(
            input_dir=str(input_dir),
            processed_dir=str(processed_dir),
            scheduler=scheduler
        )

        assert tasks_added == 3