"""RAG: разбор запроса на корни слов и ранжирование мест города.
Автор: Антон

Шаг «Retrieval» в RAG: из нашей базы выбираются и сортируются места,
которые лучше всего подходят под запрос. Нейросеть места не придумывает."""

import re

from data.places import PLACES
from travel.text import low, has
from travel.planner import kind_of

# слова, которые ничего не говорят о желаниях: их не ищем
SKIP = ["хочу", "хоти", "нужно", "можно", "куда", "едем", "поеде", "какие", "какой", "есть", "место", "места",
        "день", "дня", "дней", "один", "одног", "двух", "трех", "чтобы", "очень", "любим", "люблю",
        "москв", "лимас", "кипр", "барсе", "испан", "токио", "япони", "сидне", "австр", "париж", "франц"]

# если в запросе есть слово слева — ищем в описаниях мест слова справа
SYNONYMS = {
    "гуля":     ["парк", "сад", "набережн", "променад"],
    "прогул":   ["парк", "сад", "набережн", "променад"],
    "природ":   ["парк", "сад", "лес", "пруд", "озер"],
    "мор":      ["пляж", "набережн", "марин", "гаван", "океан"],
    "пляж":     ["пляж", "океан", "набережн"],
    "вид":      ["смотров", "панорам", "вид"],
    "истори":   ["истори", "крепост", "замок", "средневек", "музе"],
    "архитект": ["собор", "храм", "башн", "дворец", "гауди"],
    "искусств": ["искусств", "галере", "картин", "импрессион"],
    "животн":   ["зоопарк", "москвариум", "аквариум"],
    "романт":   ["закат", "вид", "смотров", "набережн"],
    "дешев":    ["фастфуд", "недорог", "быстро"],
    "вкусн":    ["ресторан", "кухн", "michelin"],
}


def query_words(text):
    """Корни слов запроса (первые 5 букв), без коротких и пустых слов."""
    result = []
    for word in re.split(r"[^а-яa-z0-9]+", low(text)):
        if len(word) <= 3:
            continue
        root = word[:5]
        if has(root, SKIP) or root in SKIP:
            continue
        if root not in result:
            result.append(root)
    return result


def find_places(city, text, wishes):
    """Все места города, отсортированные от самых подходящих к наименее подходящим."""
    t = low(text)
    words = query_words(text)
    found = []
    for place in PLACES:
        if place["city"] != city:
            continue
        info = low(place["name"] + " " + place["about"] + " " + place["type"])
        score = 0
        for w in words:              # совпало слово запроса — +2
            if w in info:
                score += 2
        for key, similar in SYNONYMS.items():   # совпал синоним — +1
            if key in t:
                for s in similar:
                    if s in info:
                        score += 1
        kind = kind_of(place)        # бонусы за выбранные пожелания
        if "Музеи" in wishes and kind == "музей":
            score += 2
        if "Гастро" in wishes and kind == "ужин":
            score += 2
        if "Бюджетно" in wishes and kind == "обед":
            score += 2
        if "С детьми" in wishes and place["kids"]:
            score += 1
        if "В дождь" in wishes and place["rain"]:
            score += 1
        found.append((score, place))
    found.sort(key=lambda f: f[0], reverse=True)   # сортировка устойчивая, как в JS
    return [place for score, place in found]
