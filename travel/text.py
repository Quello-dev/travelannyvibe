"""Утилиты для работы с текстом запроса.
Автор: Лиза"""


def low(text):
    """Нижний регистр и «ё» → «е», чтобы «ребёнок» и «ребенок» искались одинаково."""
    return text.lower().replace("ё", "е")


def has(text, words):
    """Есть ли в тексте хотя бы одно слово из списка."""
    return any(w in text for w in words)


def all_text(state):
    """Весь диалог одним текстом: запрос + ответы на вопросы."""
    return "\n".join([state["text"]] + [qa["answer"] for qa in state["qa"]])
