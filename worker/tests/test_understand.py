"""Текст → операции: цепочка провайдер → извлечение JSON → валидатор.

Провайдер подменяем: тесты не ходят в сеть и проверяют именно защиту от
некорректных ответов модели.
"""

import pytest

from mixpilot_worker.errors import AppError
from mixpilot_worker.llm import understand


class FakeProvider:
    def __init__(self, answer: str):
        self.answer = answer
        self.calls: list[tuple[str, str]] = []

    def complete(self, system, user, *, quality=False, max_tokens=0):
        self.calls.append((system, user))
        return self.answer


@pytest.fixture()
def fake(monkeypatch):
    def install(answer: str) -> FakeProvider:
        provider = FakeProvider(answer)
        monkeypatch.setattr(understand, "get_provider", lambda: provider)
        return provider

    return install


def test_ops_from_fenced_json(fake):
    # так отвечает реальный посредник
    fake('```json\n{"ops":[{"op":"bass","amount":1},{"op":"intro_shorter"}],"summary_ru":"бас мощнее"}\n```')
    res = understand.text_to_ops("бас мощнее и вступление короче")
    assert res["ops"] == [{"op": "bass", "amount": 1}, {"op": "intro_shorter"}]
    assert res["summary_ru"] == "бас мощнее"


def test_context_reaches_prompt(fake):
    provider = fake('{"ops":[{"op":"air","db":2}],"summary_ru":"ярче"}')
    understand.text_to_ops("ярче", {"style_name": "Phonk", "bpm": 92, "sections": ["вступление", "припев"]})
    _system, user = provider.calls[0]
    assert "Phonk" in user and "92" in user and "припев" in user


def test_garbage_ops_rejected(fake):
    # посредник вернул строки вместо объектов — до звука дойти не должно
    fake('{"ops":["intro_shorter","bass(1)"],"summary_ru":"x"}')
    with pytest.raises(AppError) as err:
        understand.text_to_ops("что-нибудь")
    assert err.value.code == "E_DSL"


def test_unknown_op_rejected(fake):
    fake('{"ops":[{"op":"delete_all_files"}],"summary_ru":"x"}')
    with pytest.raises(AppError) as err:
        understand.text_to_ops("сделай что-нибудь")
    assert err.value.code == "E_DSL"


def test_empty_ops_gives_friendly_message(fake):
    fake('{"ops":[],"summary_ru":"не понял"}')
    with pytest.raises(AppError) as err:
        understand.text_to_ops("привет как дела")
    assert err.value.code == "E_DSL"
    assert "привет как дела" in err.value.message_ru


def test_unparseable_answer(fake):
    fake("Извините, я не могу помочь с этим.")
    with pytest.raises(AppError) as err:
        understand.text_to_ops("бас мощнее")
    assert err.value.code == "E_DSL"


def test_empty_text_rejected_without_network(fake):
    provider = fake('{"ops":[]}')
    with pytest.raises(AppError):
        understand.text_to_ops("   ")
    assert provider.calls == []  # в облако не ходили


def test_plan_picks_known_style(fake):
    fake('{"style":"club","ops":[{"op":"bass","amount":2}],"summary_ru":"клубно"}')
    plan = understand.text_to_plan("хочу клубный трек")
    assert plan["style"] == "club" and plan["ops"][0]["amount"] == 2


def test_plan_ignores_unknown_style_and_bad_ops(fake):
    fake('{"style":"reggaeton","ops":[{"op":"nope"}],"summary_ru":"x"}')
    plan = understand.text_to_plan("что-то необычное")
    assert plan["style"] == ""  # выберем сами по анализу трека
    assert plan["ops"] == []
