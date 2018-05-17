import pytest

@pytest.mark.parametrize('path, match', [
    # search term requires a minimum of 3 characters
    ('/search?q=en', '[{"message": "Query must be at least 3 characters."}]'),
    # languages can be searched by iso (which counts as an identifier)
    ('/search?q=lzh', '[{"glottocode": "lite1248", "iso": "lzh", "name": "Literary Chinese", "matched_identifiers": ["lzh"], "level": "language"}]'),
    # languages can be searched by glottocode
    ('/search?q=kumy1244', '[{"glottocode": "kumy1244", "iso": "kum", "name": "Kumyk", "matched_identifiers": [], "level": "language"}]'),
    # Multilingual set to false
    ('/search?q=anglai&multilingual=false', '[]'),
    # multilingual indentifier matching allows more results. The results are ordered by identifier similarity
    ('/search?q=anglai&multilingual=true', '[{"glottocode": "stan1293", "iso": "eng", "name": "English", "matched_identifiers": ["anglais", "Anglais moderne"], "level": "language"}, {"glottocode": "midd1317", "iso": "enm", "name": "Middle English", "matched_identifiers": ["anglais moyen (1100-1500)", "Moyen anglais"], "level": "language"}, {"glottocode": "tsha1245", "iso": "tsj", "name": "Tshangla", "matched_identifiers": ["Tshanglaish"], "level": "language"}]'),
    # partial word matching set by default
    ('/search?q=klar', '[{"glottocode": "kumy1244", "iso": "kum", "name": "Kumyk", "matched_identifiers": ["Kumuklar"], "level": "language"}]'),
    # whole word matching removes partial-match results
    ('/search?q=klar&whole=true', '[]'),
    # whole word match successful
    ('/search?q=Literary%20Chinese&whole=true', '[{"glottocode": "lite1248", "iso": "lzh", "name": "Literary Chinese", "matched_identifiers": ["Literary Chinese"], "level": "language"}]'),
])

def test_search_api(app, path, match):
    kwargs = {'status': 200}
    res = app.get(path, **kwargs)
    if match is not None:
        assert match in res

@pytest.mark.parametrize('path, status, match', [
    # generic English
    ('/languoid/stan1293', 200, '"id": "stan1293", "name": "English", "level": "Language"'),
    # glottocode with proper format that doesn't exist
    ('/languoid/test1111', 404, '"error"'),
    # glottocode with improper format
    ('/languoid/test11111', 404, '"error"'),
])
def test_languoid_get(app, path, status, match):
    res = app.get(path, {'status': status}, expect_errors=True)
    assert match in res
