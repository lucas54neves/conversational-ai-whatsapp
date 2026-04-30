def test_smoke(db_url):
    assert db_url.startswith("postgresql://")
