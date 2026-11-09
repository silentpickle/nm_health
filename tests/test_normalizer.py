import unittest
from nm_health.ingest.normalizer import normalize_address, normalize_establishment_name


class TestNormalizer(unittest.TestCase):
    def test_normalize_address_standard(self):
        res = normalize_address("1700 TOWNE CENTER LN SE")
        self.assertEqual(res["street_number"], "1700")
        self.assertEqual(res["street_name"], "TOWNE CENTER LN")
        self.assertEqual(res["quadrant"], "SE")
        self.assertEqual(res["normalized_address"], "1700 TOWNE CENTER LN SE")

    def test_normalize_address_with_unit(self):
        res = normalize_address("1415 4TH ST SW, H")
        self.assertEqual(res["street_number"], "1415")
        self.assertEqual(res["street_name"], "4TH ST")
        self.assertEqual(res["quadrant"], "SW")
        self.assertEqual(res["unit"], "H")
        self.assertEqual(res["normalized_address"], "1415 4TH ST SW, Unit H")

    def test_normalize_establishment_name(self):
        name = normalize_establishment_name("  BUFFALO WILD WINGS 613 - ")
        self.assertEqual(name, "BUFFALO WILD WINGS 613")


if __name__ == "__main__":
    unittest.main()
