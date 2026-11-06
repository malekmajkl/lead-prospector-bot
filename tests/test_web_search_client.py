from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_duckduckgo_route(monkeypatch):
    monkeypatch.setenv("SEARCH_PROVIDER", "duckduckgo")
    monkeypatch.setenv("LLM_PROVIDER", "local")

    mock_results = [
        {"title": "Obecní úřad Zlín", "href": "https://zlin.cz/starosta", "body": "Starosta Zlína Ing. Jan Novák"},
        {"title": "Kontakty", "href": "https://zlin.cz/kontakty", "body": "email: novak@zlin.cz"},
    ]

    with patch("core.web_search_client.SEARCH_PROVIDER", "duckduckgo"):
        ddgs_instance = MagicMock()
        ddgs_instance.text.return_value = mock_results
        with patch("core.web_search_client._duckduckgo") as mock_ddg:
            mock_ddg.return_value = "[Obecní úřad Zlín] https://zlin.cz/starosta\nStarosta Zlína"
            from core.web_search_client import web_search
            result = web_search("starosta zlín email")

    mock_ddg.assert_called_once_with("starosta zlín email", 8)
    assert "Obecní úřad Zlín" in result


def test_serpapi_route(monkeypatch):
    monkeypatch.setenv("SEARCH_PROVIDER", "serpapi")
    monkeypatch.setenv("SERPAPI_KEY", "test-key")

    with patch("core.web_search_client.SEARCH_PROVIDER", "serpapi"):
        with patch("core.web_search_client._serpapi") as mock_serp:
            mock_serp.return_value = "[Zlín] https://zlin.cz\nStarosta kontakt"
            from core.web_search_client import web_search
            result = web_search("starosta zlín", num_results=5)

    mock_serp.assert_called_once_with("starosta zlín", 5)
    assert "Zlín" in result


def test_duckduckgo_formats_output():
    mock_results = [
        {"title": "Title A", "href": "https://example.cz/a", "body": "Body A"},
        {"title": "Title B", "href": "https://example.cz/b", "body": "Body B"},
    ]
    with patch("duckduckgo_search.DDGS") as mock_ddgs_cls:
        instance = mock_ddgs_cls.return_value.__enter__.return_value
        instance.text.return_value = mock_results
        mock_ddgs_cls.return_value.text = MagicMock(return_value=mock_results)

        from core.web_search_client import _duckduckgo
        result = _duckduckgo("test query", 2)

    assert "[Title A] https://example.cz/a" in result
    assert "Body A" in result
    assert "[Title B] https://example.cz/b" in result


def test_serpapi_formats_output():
    import json
    from unittest.mock import patch

    fake_response = {
        "organic_results": [
            {"title": "Obec Luhačovice", "link": "https://luhacovice.cz", "snippet": "Starosta obce"},
        ]
    }
    mock_resp = MagicMock()
    mock_resp.json.return_value = fake_response

    with patch("requests.get", return_value=mock_resp):
        with patch("core.web_search_client.SERPAPI_KEY", "test-key"):
            from core.web_search_client import _serpapi
            result = _serpapi("starosta luhacovice", 3)

    assert "[Obec Luhačovice] https://luhacovice.cz" in result
    assert "Starosta obce" in result
