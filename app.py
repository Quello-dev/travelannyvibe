"""TravelAnyVibe — сайт на Python (Flask).
Автор: Лиза (приложение и экраны)

Как работает: каждый экран — отдельный адрес. Браузер присылает нажатие или форму,
Python обновляет «блокнот» пользователя (state) и отдаёт готовую страницу.

Запуск:  python3 app.py   (на Windows: python app.py) — сайт откроется в браузере сам.
"""

import os
import socket
import sys
import uuid
import webbrowser

try:
    from flask import Flask, redirect, render_template, request, session
except ImportError:
    sys.exit("Не установлен Flask. Выполните в терминале:  python3 -m pip install flask\n"
             "(на Windows:  python -m pip install flask)")

from data.cities import CITIES
from data.places import PLACES
from travel import ai, assets, planner, rag
from travel.questions import MAX_QUESTIONS, next_question
from travel.text import all_text
from travel.wishes import WISHES, find_days, find_wishes

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(24)

# картинки, значки и справочники доступны во всех шаблонах
app.jinja_env.globals.update(ART=assets.ART, LOGO=assets.LOGO, ICONS=assets.ICONS, torn=assets.torn,
                             CITIES=CITIES, PLACES=PLACES, LABELS=planner.LABELS)

START_TEXT = "Я путешествую с грудным ребёнком и мужем. Хотим активный отдых на 3 дня, чтобы было комфортно и ребёнку, и нам."

# «Блокноты» пользователей хранятся в памяти сервера. В cookie браузера лежит только номер блокнота.
STATES = {}


def new_state():
    return {
        "text": START_TEXT,
        "wishes": find_wishes(START_TEXT),
        "days": find_days(START_TEXT) or 3,
        "qa": [],          # ответы на вопросы: [{"question": ..., "answer": ...}]
        "city": None,      # город, выбранный DeepSeek
        "reasons": [],     # 3 причины выбора
        "route": [],       # маршрут: список дней
        "legs": {},        # время в пути по дням: {0: [{"minutes", "km"}]}
        "addresses": {},   # адреса мест от DeepSeek: {"Название": "адрес"}
        "error": "",       # текст ошибки над кнопкой
    }


def get_state():
    """Блокнот текущего пользователя (создаётся при первом заходе)."""
    sid = session.get("id")
    if sid not in STATES:
        sid = session["id"] = uuid.uuid4().hex
        STATES[sid] = new_state()
    return STATES[sid]


def theme(state):
    """Цвета телефона: на экранах города и маршрута — цвета выбранного города."""
    c = CITIES.get(state["city"]) or {"color": "#56622F", "accent": "#E0A526", "bg": "#F4EDE1"}
    return f"--main:{c['color']};--accent:{c['accent']};--bg:{c['bg']}"


def finish(state):
    """Отправляет весь диалог в DeepSeek и переходит к экрану города."""
    try:
        state["city"], state["reasons"] = ai.choose_city(state, CITIES)
    except ai.AIError as e:
        state["error"] = f"DeepSeek не ответил: {e}"
        return redirect("/questions" if state["qa"] else "/")
    state["error"] = ""
    return redirect("/city")


# ---------- Экран 1: старт ----------

@app.get("/")
def start():
    state = get_state()
    return render_template("start.html", s=state, wishes=WISHES, theme=theme({"city": None}))


@app.post("/start")
def start_submit():
    state = get_state()
    state["text"] = request.form.get("text", "").strip() or START_TEXT
    chosen = request.form.getlist("wish")
    state["wishes"] = [w for w in WISHES if w in chosen or w in find_wishes(state["text"])]
    state["days"] = int(request.form.get("days") or find_days(state["text"]) or 3)
    state["qa"] = []
    state["error"] = ""
    if next_question(state):
        return redirect("/questions")
    return finish(state)


# ---------- Экран 2: уточняющие вопросы ----------

@app.get("/questions")
def questions():
    state = get_state()
    return render_template("questions.html", s=state, q=next_question(state), max_q=MAX_QUESTIONS,
                           theme=theme({"city": None}))


@app.post("/answer")
def answer():
    state = get_state()
    text = request.form.get("answer", "").strip()
    q = next_question(state)
    if text and q:
        state["qa"].append({"question": q["question"], "answer": text})
        for wish in find_wishes(text):
            if wish not in state["wishes"]:
                state["wishes"].append(wish)
        if find_days(text):
            state["days"] = find_days(text)
    if next_question(state):
        return redirect("/questions")
    return finish(state)


@app.post("/finish")
def finish_now():
    return finish(get_state())


# ---------- Экран 3: лучшее совпадение ----------

@app.get("/city")
def city():
    state = get_state()
    if not state["city"]:
        return redirect("/")
    count = sum(1 for p in PLACES if p["city"] == state["city"])
    return render_template("city.html", s=state, c=CITIES[state["city"]], count=count, theme=theme(state))


# ---------- Экран 4: маршрут ----------

@app.post("/route")
def route_build():
    state = get_state()
    places = rag.find_places(state["city"], all_text(state), state["wishes"])   # 1) RAG ищет места
    state["route"] = planner.build_route(places, state["days"], state["wishes"])  # 2) раскладываем по часам
    state["legs"] = {}
    return redirect("/route?day=0")


def load_legs(state, d):
    """Один раз на каждый день спрашивает DeepSeek адреса и время в пути."""
    day = state["route"][d]
    if d in state["legs"] or len(day) < 2:
        return
    country = CITIES[state["city"]]["country"]
    try:
        addresses, legs = ai.find_legs(state["city"], country, day)
    except ai.AIError:
        state["legs"][d] = []          # не вышло — покажем время по расписанию
        return
    for item, address in zip(day, addresses):
        if address:
            state["addresses"][item["place"]["name"]] = address
    state["legs"][d] = legs


def address_of(state, place):
    return place.get("address") or state["addresses"].get(place["name"], "")


@app.get("/route")
def route():
    state = get_state()
    if not state["route"]:
        return redirect("/city" if state["city"] else "/")
    d = min(max(request.args.get("day", 0, type=int), 0), len(state["route"]) - 1)
    load_legs(state, d)
    day, legs = state["route"][d], state["legs"].get(d)
    rows = []
    for i, item in enumerate(day):
        road = ""
        if i > 0:
            prev = day[i - 1]
            gap = planner.minutes_of(item["time"]) - planner.minutes_of(prev["time"]) - prev["minutes"]
            road = ai.road_text(legs, i - 1, gap)
        p = item["place"]
        tags = [p["type"]] + (["с детьми"] if p["kids"] else []) + (["в дождь"] if p["rain"] else []) + ([p["price"]] if p["price"] else [])
        rows.append({"item": item, "road": road, "tags": " · ".join(tags),
                     "address": address_of(state, p), "hours": planner.hours(item["minutes"])})
    return render_template("route.html", s=state, d=d, rows=rows, ai_legs=bool(legs), theme=theme(state))


# ---------- Экран 5: карточка места ----------

@app.get("/place/<int:d>/<int:i>")
def place(d, i):
    state = get_state()
    if d >= len(state["route"]) or i >= len(state["route"][d]):
        return redirect("/route")
    item = state["route"][d][i]
    p = item["place"]
    extra_title, extra = "С детьми · в дождь", ("да" if p["kids"] else "нет") + " · " + ("да" if p["rain"] else "нет")
    if p["type"] == "кафе":
        extra_title, extra = "Кухня", "быстро, недорого"
    if p["type"] == "ресторан":
        extra_title, extra = "Кухня", "высокая кухня"
    end = planner.time_of(planner.minutes_of(item["time"]) + item["minutes"])
    return render_template("place.html", s=state, d=d, item=item, p=p, end=end, c=CITIES[state["city"]],
                           extra_title=extra_title, extra=extra, address=address_of(state, p),
                           why=planner.why(item, state["wishes"]), theme=theme(state))


def free_port(start=8000):
    """Первый свободный порт, начиная с 8000. Порт 5000 на Mac занят AirPlay, поэтому его не берём."""
    for port in range(start, start + 50):
        with socket.socket() as sock:
            if sock.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return start


if __name__ == "__main__":
    port = int(os.environ.get("PORT") or free_port())
    url = f"http://127.0.0.1:{port}"
    print(f"TravelAnyVibe запущен: {url}\nЧтобы остановить — нажмите Ctrl+C в этом окне.")
    webbrowser.open(url)
    app.run(host="127.0.0.1", port=port, debug=False)
