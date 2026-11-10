import unittest  # noqa: CPY001, D100, I001
from nm_health.ingest.normalizer import normalize_address, normalize_establishment_name


class TestNormalizer(unittest.TestCase):  # noqa: D101
    def test_normalize_address_standard(self):  # noqa: ANN201, D102
        res = normalize_address("1700 TOWNE CENTER LN SE")
        self.assertEqual(res["street_number"], "1700")  # noqa: PT009
        self.assertEqual(res["street_name"], "TOWNE CENTER LN")  # noqa: PT009
        self.assertEqual(res["quadrant"], "SE")  # noqa: PT009
        self.assertEqual(res["normalized_address"], "1700 TOWNE CENTER LN SE")  # noqa: PT009

    def test_normalize_address_with_unit(self):  # noqa: ANN201, D102
        res = normalize_address("1415 4TH ST SW, H")
        self.assertEqual(res["street_number"], "1415")  # noqa: PT009
        self.assertEqual(res["street_name"], "4TH ST")  # noqa: PT009
        self.assertEqual(res["quadrant"], "SW")  # noqa: PT009
        self.assertEqual(res["unit"], "H")  # noqa: PT009
        self.assertEqual(res["normalized_address"], "1415 4TH ST SW, Unit H")  # noqa: PT009

    def test_normalize_establishment_name(self):  # noqa: ANN201, D102
        name = normalize_establishment_name("  BUFFALO WILD WINGS 613 - ")
        self.assertEqual(name, "BUFFALO WILD WINGS 613")  # noqa: PT009


if __name__ == "__main__":
    unittest.main()
