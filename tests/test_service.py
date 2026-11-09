import unittest  # noqa: CPY001, D100, I001
import tempfile
from unittest import mock
from pathlib import Path
from nm_health.db.local_store import LocalStore
from nm_health.ingest.parser import InspectionReportParser
from nm_health.ingest.fetcher import ReportFetcher


class TestServiceEndToEnd(unittest.TestCase):  # noqa: D101
    @classmethod
    def setUpClass(cls):  # noqa: ANN206, D102
        cls.sample_pdf = Path(__file__).resolve().parent.parent / "sample_inspection_report.pdf"
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.temp_db = Path(cls.temp_dir.name) / "test.db"
        cls.store = LocalStore(db_path=cls.temp_db)
        # ingest_file copies the PDF into ARCHIVE_DIR: point it at the temp dir, never the real archive.
        cls.archive_patch = mock.patch("nm_health.ingest.fetcher.ARCHIVE_DIR", Path(cls.temp_dir.name))
        cls.archive_patch.start()

    @classmethod
    def tearDownClass(cls):  # noqa: ANN206, D102
        cls.archive_patch.stop()
        cls.temp_dir.cleanup()

    def test_01_parser_sample(self):  # noqa: ANN201, D102
        self.assertTrue(self.sample_pdf.exists(), "sample_inspection_report.pdf must exist")  # noqa: PT009
        parser = InspectionReportParser(self.sample_pdf)
        data = parser.parse()
        self.assertGreater(data["total_establishments"], 40)  # noqa: PT009
        self.assertGreater(data["total_inspections"], 70)  # noqa: PT009
        self.assertEqual(data["metadata"]["week_start"], "September 20, 2026")  # noqa: PT009

    def test_02_ingest_and_query(self):  # noqa: ANN201, D102
        fetcher = ReportFetcher(store=self.store)
        res = fetcher.ingest_file(self.sample_pdf, force=True)
        self.assertEqual(res["status"], "success")  # noqa: PT009
        self.assertGreater(res["total_establishments"], 40)  # noqa: PT009

        # Test search
        results = self.store.search_establishments("CALIFORNIA DEL NORTE")
        self.assertGreater(len(results), 0)  # noqa: PT009
        est = results[0]
        self.assertIn("1415", est["normalized_address"])  # noqa: PT009

        # Test detail
        detail = self.store.get_establishment_detail(est["id"])
        self.assertIsNotNone(detail)  # noqa: PT009
        self.assertGreaterEqual(len(detail["inspections"]), 2)  # noqa: PT009

        # Test pest search
        pest_results = self.store.search_establishments("cockroach")
        self.assertGreaterEqual(len(pest_results), 1)  # noqa: PT009

    def test_03_stats(self):  # noqa: ANN201, D102
        stats = self.store.get_stats()
        self.assertGreater(stats["total_establishments"], 0)  # noqa: PT009
        self.assertGreater(stats["total_violations"], 100)  # noqa: PT009
        self.assertGreater(stats["total_closures"], 0)  # noqa: PT009


if __name__ == "__main__":
    unittest.main()
