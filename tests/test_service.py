import unittest
import tempfile
from pathlib import Path
from nm_health.db.local_store import LocalStore
from nm_health.ingest.parser import InspectionReportParser
from nm_health.ingest.fetcher import ReportFetcher


class TestServiceEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sample_pdf = Path(__file__).resolve().parent.parent / "sample_inspection_report.pdf"
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.temp_db = Path(cls.temp_dir.name) / "test.db"
        cls.store = LocalStore(db_path=cls.temp_db)

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def test_01_parser_sample(self):
        self.assertTrue(self.sample_pdf.exists(), "sample_inspection_report.pdf must exist")
        parser = InspectionReportParser(self.sample_pdf)
        data = parser.parse()
        self.assertGreater(data["total_establishments"], 40)
        self.assertGreater(data["total_inspections"], 70)
        self.assertEqual(data["metadata"]["week_start"], "September 20, 2026")

    def test_02_ingest_and_query(self):
        fetcher = ReportFetcher(store=self.store)
        res = fetcher.ingest_file(self.sample_pdf, force=True)
        self.assertEqual(res["status"], "success")
        self.assertGreater(res["total_establishments"], 40)

        # Test search
        results = self.store.search_establishments("CALIFORNIA DEL NORTE")
        self.assertGreater(len(results), 0)
        est = results[0]
        self.assertIn("1415", est["normalized_address"])

        # Test detail
        detail = self.store.get_establishment_detail(est["id"])
        self.assertIsNotNone(detail)
        self.assertGreaterEqual(len(detail["inspections"]), 2)

        # Test pest search
        pest_results = self.store.search_establishments("cockroach")
        self.assertGreaterEqual(len(pest_results), 1)

    def test_03_stats(self):
        stats = self.store.get_stats()
        self.assertGreater(stats["total_establishments"], 0)
        self.assertGreater(stats["total_violations"], 100)
        self.assertGreater(stats["total_closures"], 0)


if __name__ == "__main__":
    unittest.main()
