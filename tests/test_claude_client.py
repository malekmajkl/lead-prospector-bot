from __future__ import annotations

import pytest

from core.claude_client import parse_json_response


class TestParseJsonResponse:
    def test_plain_array(self):
        raw = '[{"a": 1}, {"b": 2}]'
        result = parse_json_response(raw)
        assert result == [{"a": 1}, {"b": 2}]

    def test_plain_object(self):
        raw = '{"key": "value"}'
        result = parse_json_response(raw)
        assert result == {"key": "value"}

    def test_strips_json_fence(self):
        raw = '```json\n[{"x": 1}]\n```'
        result = parse_json_response(raw)
        assert result == [{"x": 1}]

    def test_strips_plain_fence(self):
        raw = '```\n[{"x": 1}]\n```'
        result = parse_json_response(raw)
        assert result == [{"x": 1}]

    def test_extracts_array_from_surrounding_text(self):
        raw = 'Here are the results:\n[{"name": "Brno"}]\nDone.'
        result = parse_json_response(raw)
        assert result == [{"name": "Brno"}]

    def test_returns_none_on_invalid_json(self):
        raw = "this is not json at all"
        result = parse_json_response(raw)
        assert result is None

    def test_returns_none_on_empty_string(self):
        result = parse_json_response("")
        assert result is None

    def test_unicode_preserved(self):
        raw = '[{"municipality": "Kroměříž", "role": "starosta"}]'
        result = parse_json_response(raw)
        assert result[0]["municipality"] == "Kroměříž"

    def test_multiline_array(self):
        raw = '[\n  {"a": 1},\n  {"b": 2}\n]'
        result = parse_json_response(raw)
        assert len(result) == 2
