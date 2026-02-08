import unittest


from citecontext.pipeline import _pick_earliest_publishing_author


class _FakeClient:
    def __init__(self, mapping):
        self.mapping = mapping

    def get_author_earliest_publication_year(self, author_id: str, *, max_year=None, **_kwargs):
        year = self.mapping.get(author_id)
        if year is None:
            return None
        if max_year is not None and year > max_year:
            return None
        return year


class TestEarliestAuthor(unittest.TestCase):
    def test_pick_earliest_author(self):
        paper = {
            "authors": [
                {"authorId": "a1", "name": "Alice"},
                {"authorId": "a2", "name": "Bob"},
                {"authorId": "a3", "name": "Carol"},
            ]
        }
        client = _FakeClient({"a1": 2010, "a2": 1999, "a3": 2005})
        cache = {}

        chosen = _pick_earliest_publishing_author(client, paper, earliest_year_cache=cache, cutoff_year=None)
        self.assertEqual(chosen["authorId"], "a2")
        self.assertEqual(chosen["name"], "Bob")
        self.assertEqual(chosen["earliest_publication_year"], 1999)

    def test_fallback_when_unknown(self):
        paper = {"authors": [{"name": "NoId"}]}
        client = _FakeClient({})
        cache = {}

        chosen = _pick_earliest_publishing_author(client, paper, earliest_year_cache=cache, cutoff_year=2015)
        self.assertEqual(chosen["name"], "NoId")
        self.assertIsNone(chosen["earliest_publication_year"])

    def test_cutoff_year_skips_new_authors(self):
        paper = {
            "authors": [
                {"authorId": "a1", "name": "Alice"},
                {"authorId": "a2", "name": "Bob"},
            ]
        }
        client = _FakeClient({"a1": 2018, "a2": 2010})
        cache = {}

        chosen = _pick_earliest_publishing_author(client, paper, earliest_year_cache=cache, cutoff_year=2015)
        self.assertEqual(chosen["authorId"], "a2")
        self.assertEqual(chosen["earliest_publication_year"], 2010)


if __name__ == "__main__":
    unittest.main()
