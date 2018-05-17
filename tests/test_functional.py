import pytest

@pytest.mark.parametrize('method, path, status, match', [
    # search term requires a minimum of 3 characters
    ('get', '/search?q=en', None, '[{"message": "Query must be at least 3 characters."}]'),
    # languages can be searched by iso (which counts as an identifier)
    ('get', '/search?q=lzh', None, '[{"glottocode": "lite1248", "iso": "lzh", "name": "Literary Chinese", "matched_identifiers": ["lzh"], "level": "language"}]'),
    # languages can be searched by glottocode
    ('get', '/search?q=kumy1244', None, '[{"glottocode": "kumy1244", "iso": "kum", "name": "Kumyk", "matched_identifiers": [], "level": "language"}]'),
    # Multilingual set to false
    ('get', '/search?q=anglai&multilingual=false', None, '[]'),
    # multilingual indentifier matching allows more results. The results are ordered by identifier similarity
    ('get', '/search?q=anglai&multilingual=true', None, '[{"glottocode": "stan1293", "iso": "eng", "name": "English", "matched_identifiers": ["anglais", "Anglais moderne"], "level": "language"}, {"glottocode": "midd1317", "iso": "enm", "name": "Middle English", "matched_identifiers": ["anglais moyen (1100-1500)", "Moyen anglais"], "level": "language"}, {"glottocode": "tsha1245", "iso": "tsj", "name": "Tshangla", "matched_identifiers": ["Tshanglaish"], "level": "language"}]'),
    # partial word matching set by default
    ('get', '/search?q=klar', None, '[{"glottocode": "kumy1244", "iso": "kum", "name": "Kumyk", "matched_identifiers": ["Kumuklar"], "level": "language"}]'),
    # whole word matching removes partial-match results
    ('get', '/search?q=klar&whole=true', None, '[]'),
    # whole word match successful
    ('get', '/search?q=Literary%20Chinese&whole=true', None, '[{"glottocode": "lite1248", "iso": "lzh", "name": "Literary Chinese", "matched_identifiers": ["Literary Chinese"], "level": "language"}]'),
])

def test_search_api(app, method, path, status, match):
    kwargs = {'status': status} if status is not None else {'status': 200}
    res = getattr(app, method)(path, **kwargs)
    if match is not None:
        assert match in res
