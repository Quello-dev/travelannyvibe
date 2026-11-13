"""Работа с DeepSeek через Zveno.ai: выбор лучшего города, адреса мест и время в пути.
Автор: Андрей

Ключ хранится только на сервере, в файле .env — в браузер он не попадает."""

import json
import os
import urllib.error
import urllib.request

API_URL = "https://api.zveno.ai/v1/chat/completions"


def load_env():
    """Читает файл .env рядом с app.py: строки вида AI_KEY=... попадают в настройки."""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                name, value = line.split("=", 1)
                os.environ.setdefault(name.strip(), value.strip().strip("'\""))


load_env()


class AIError(Exception):
    """Ошибка нейросети: текст показывается пользователю над кнопкой."""


def ask_ai(system, user):
    """Отправляет нейросети инструкцию (system) и данные (user), возвращает ответ как словарь."""
    key = os.environ.get("AI_KEY", "")
    if not key or key.startswith("СЮДА"):
        raise AIError("ключ не задан — впишите AI_KEY в файл .env")
    body = json.dumps({
        "model": os.environ.get("AI_MODEL", "deepseek/deepseek-v4.1-flash"),
        "temperature": 0.2,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }).encode("utf-8")
    request = urllib.request.Request(
        os.environ.get("AI_URL", API_URL), data=body, method="POST",
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.load(response)
    except urllib.error.HTTPError as e:
        raise AIError(f"Zveno ответил {e.code}: {e.read().decode('utf-8', 'replace')[:200]}")
    except (urllib.error.URLError, TimeoutError):
        raise AIError("нет связи с Zveno — проверьте интернет")
    try:
        text = data["choices"][0]["message"]["content"]
        return json.loads(text[text.index("{"): text.rindex("}") + 1])   # вырезаем JSON из ответа
    except (KeyError, IndexError, ValueError):
        raise AIError("непонятный ответ модели, попробуйте ещё раз")


def choose_city(state, cities):
    """Просит DeepSeek выбрать ОДИН город под весь диалог. Возвращает (город, причины)."""
    city_list = ", ".join(f"{name} ({c['country']})" for name, c in cities.items())
    dialog = "Запрос: " + state["text"]
    for qa in state["qa"]:
        dialog += "\nВопрос: " + qa["question"] + "\nОтвет: " + qa["answer"]
    dialog += "\nПожелания: " + (", ".join(state["wishes"]) or "нет") + "\nДней: " + str(state["days"])
    answer = ask_ai(
        "Ты — тревел-ассистент приложения TravelAnyVibe. Выбери ровно ОДИН город из списка: " + city_list +
        ". Учитывай весь диалог: кто едет, темп, интересы, бюджет, число дней. "
        "Если человек сам назвал город или страну из списка — выбери его. "
        'Ответь только JSON без пояснений: {"city": "название города точно как в списке, без страны", '
        '"reasons": ["причина 1", "причина 2", "причина 3"]}. '
        "Каждая причина — до 8 слов, по-русски, про этот запрос.",
        dialog,
    )
    city, reasons = answer.get("city"), answer.get("reasons")
    if city not in cities or not isinstance(reasons, list):   # защита: только город из нашего списка
        raise AIError("модель назвала город не из списка, попробуйте ещё раз")
    return city, [str(r) for r in reasons[:3]]


def find_legs(city, country, day):
    """Адреса мест одного дня и время на машине между соседними точками.
    Возвращает (адреса, отрезки), отрезок = {"minutes": 15, "km": 6.5}."""
    n = len(day)
    places = "\n".join(
        f"{i + 1}. {item['place']['name']}" + (f" (адрес из базы: {item['place']['address']})" if item["place"].get("address") else "")
        for i, item in enumerate(day)
    )
    answer = ask_ai(
        f"Ты — помощник по маршрутам в городе {city} ({country}). "
        "Для каждого места укажи адрес (улица и дом, или ориентир). "
        "Оцени время в пути на машине между соседними точками в обычном дневном трафике. "
        'Ответь только JSON: {"places": [{"address": "..."}], "legs": [{"minutes": 15, "km": 6.5}]}. '
        f"В places ровно {n} элементов в том же порядке, в legs ровно {n - 1} (от 1-го ко 2-му, от 2-го к 3-му и т.д.).",
        "Маршрут:\n" + places,
    )
    legs = answer.get("legs")
    if not isinstance(legs, list) or len(legs) != n - 1:
        raise AIError("модель посчитала дорогу не для всех точек")
    addresses = [str(p.get("address", "")) if isinstance(p, dict) else "" for p in answer.get("places", [])]
    clean = []
    for leg in legs:
        try:
            clean.append({"minutes": round(float(leg["minutes"])), "km": float(leg.get("km") or 0)})
        except (TypeError, KeyError, ValueError):
            clean.append({"minutes": 0, "km": 0})
    return addresses, clean


def road_text(legs, i, gap):
    """Подпись между карточками маршрута: время на машине или запасной текст."""
    if legs and i < len(legs) and legs[i]["minutes"] > 0:
        text = f"≈ {legs[i]['minutes']} мин на машине"
        if legs[i]["km"]:
            text += " · " + f"{legs[i]['km']:g}".replace(".", ",") + " км"
        if legs[i]["minutes"] > gap:
            text += " · времени впритык"
        return text
    return f"{gap} мин на дорогу и отдых" if gap > 0 else "сразу дальше"
