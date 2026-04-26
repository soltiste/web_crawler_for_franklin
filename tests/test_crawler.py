# tests/test_crawler.py
import pytest
from unittest.mock import Mock, patch
from webcrowler.crowler import GeneCrawlerService
from db.domain import Variant


class TestGeneCrawlerService:
    def test_process_variants_fill_mode(self, variant_repo, mock_api_client, sample_csv_data, sample_api_response):
        mock_api_client.classify_by_coords.return_value = sample_api_response

        service = GeneCrawlerService(variant_repo, mock_api_client)
        stats = service.process_variants(sample_csv_data, mode='fill')

        assert stats['saved'] == 2
        assert stats['processed'] == 2
        assert mock_api_client.classify_by_coords.call_count == 2

    def test_process_variants_fill_mode_api_error(self, variant_repo, mock_api_client, sample_csv_data):
        mock_api_client.classify_by_coords.return_value = None

        service = GeneCrawlerService(variant_repo, mock_api_client)
        stats = service.process_variants(sample_csv_data, mode='fill')

        assert stats['errors'] == 2
        assert stats['saved'] == 0

    def test_process_variants_update_mode_no_change(self, variant_repo, mock_api_client, sample_csv_data,
                                                    sample_api_response):
        # First add variant
        mock_api_client.classify_by_coords.return_value = sample_api_response
        service = GeneCrawlerService(variant_repo, mock_api_client)
        service.process_variants(sample_csv_data[:1], mode='fill')

        # Update with same data
        stats = service.process_variants(sample_csv_data[:1], mode='update')

        assert stats['updated'] == 0
        assert stats['errors'] == 1

    def test_process_variants_update_mode_with_change(self, variant_repo, mock_api_client, sample_csv_data,
                                                      sample_api_response):
        # First add variant
        mock_api_client.classify_by_coords.return_value = sample_api_response
        service = GeneCrawlerService(variant_repo, mock_api_client)
        service.process_variants(sample_csv_data[:1], mode='fill')

        # Update with changed classification
        changed_response = sample_api_response.copy()
        changed_response['classification'] = 'Benign'
        mock_api_client.classify_by_coords.return_value = changed_response

        stats = service.process_variants(sample_csv_data[:1], mode='update')

        assert stats['updated'] == 1
        assert stats['skipped'] == 0

    def test_process_variants_update_mode_variant_not_in_db(self, variant_repo, mock_api_client, sample_csv_data,
                                                            sample_api_response):
        mock_api_client.classify_by_coords.return_value = sample_api_response
        service = GeneCrawlerService(variant_repo, mock_api_client)

        stats = service.process_variants(sample_csv_data[:1], mode='update')

        assert stats['skipped'] == 1
        assert stats['updated'] == 0

    def test_process_variants_check_mode_match(self, variant_repo, mock_api_client, sample_csv_data,
                                               sample_api_response):
        # Add variant to DB
        mock_api_client.classify_by_coords.return_value = sample_api_response
        service = GeneCrawlerService(variant_repo, mock_api_client)
        service.process_variants(sample_csv_data[:1], mode='fill')

        # Check with same data
        stats = service.process_variants(sample_csv_data[:1], mode='check')

        assert stats['processed'] == 1
        assert stats['errors'] == 0

    def test_process_variants_check_mode_mismatch(self, variant_repo, mock_api_client, sample_csv_data,
                                                  sample_api_response):
        # Add variant to DB
        mock_api_client.classify_by_coords.return_value = sample_api_response
        service = GeneCrawlerService(variant_repo, mock_api_client)
        service.process_variants(sample_csv_data[:1], mode='fill')

        # Check with changed data
        changed_response = sample_api_response.copy()
        changed_response['classification'] = 'Benign'
        mock_api_client.classify_by_coords.return_value = changed_response

        stats = service.process_variants(sample_csv_data[:1], mode='check')

        assert stats['errors'] == 1
        assert stats['processed'] == 0

    def test_process_variants_check_mode_variant_not_in_db(self, variant_repo, mock_api_client, sample_csv_data,
                                                           sample_api_response):
        mock_api_client.classify_by_coords.return_value = sample_api_response
        service = GeneCrawlerService(variant_repo, mock_api_client)

        stats = service.process_variants(sample_csv_data[:1], mode='check')

        assert stats['errors'] == 1

    def test_process_variants_invalid_row(self, variant_repo, mock_api_client):
        invalid_data = [{'chrom': '', 'pos': '0', 'ref': '', 'alt': ''}]

        service = GeneCrawlerService(variant_repo, mock_api_client)
        stats = service.process_variants(invalid_data, mode='fill')

        assert stats['processed'] == 0

    def test_process_variants_exception_handling(self, variant_repo, mock_api_client, sample_csv_data):
        mock_api_client.classify_by_coords.side_effect = Exception("API Error")

        service = GeneCrawlerService(variant_repo, mock_api_client)
        stats = service.process_variants(sample_csv_data, mode='fill')

        assert stats['errors'] == 2