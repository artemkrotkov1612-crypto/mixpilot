"""Извлечение JSON из ответов модели — включая поведение реального посредника."""

import pytest

from mixpilot_worker.llm.json_extract import JsonExtractError, extract_json_object


def test_plain_json():
    assert extract_json_object('{"ops": [{"op": "bass", "amount": 1}]}')["ops"][0]["op"] == "bass"


def test_markdown_fences():
    # именно так отвечает cheapai.io (проверено живым запросом)
    raw = '```json\n{"ops":[{"op":"intro_shorter"}]}\n```'
    assert extract_json_object(raw)["ops"] == [{"op": "intro_shorter"}]


def test_fences_without_language():
    assert extract_json_object('```\n{"a": 1}\n```')["a"] == 1


def test_prose_around_object():
    raw = 'Конечно! Вот операции:\n{"ops": [{"op": "tempo", "delta": -0.06}]}\nГотово.'
    assert extract_json_object(raw)["ops"][0]["delta"] == -0.06


def test_braces_inside_strings():
    raw = '{"hint_ru": "сделай } поярче {", "ops": []}'
    assert extract_json_object(raw)["hint_ru"] == "сделай } поярче {"


def test_escaped_quotes():
    raw = r'{"hint_ru": "скажи \"привет\"", "ops": []}'
    assert extract_json_object(raw)["hint_ru"] == 'скажи "привет"'


def test_nested_objects():
    raw = '```json\n{"ops": [{"op": "gain", "target": "vocals", "db": 2}], "meta": {"n": 1}}\n```'
    doc = extract_json_object(raw)
    assert doc["meta"]["n"] == 1 and doc["ops"][0]["target"] == "vocals"


def test_failures():
    with pytest.raises(JsonExtractError):
        extract_json_object("")
    with pytest.raises(JsonExtractError):
        extract_json_object("совсем не json")
    with pytest.raises(JsonExtractError):
        extract_json_object('[1, 2, 3]')  # массив, а не объект
