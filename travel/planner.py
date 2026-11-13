"""Сборка маршрута по часам: слоты дня, фильтры, подбор мест, время.
Автор: Лиза"""

KIND = {"кафе": "обед", "ресторан": "ужин", "музей": "музей"}
OTHER = {"прогулка": "музей", "музей": "прогулка", "обед": "ужин", "ужин": "обед"}
LABELS = {"прогулка": "Прогулка", "обед": "Обед", "музей": "Музей", "ужин": "Ужин"}


def kind_of(place):
    """Чем место будет в расписании: кафе → обед, ресторан → ужин, остальное → прогулка."""
    return KIND.get(place["type"], "прогулка")


def day_plan(wishes):
    """Шаблон одного дня, подстроенный под пожелания."""
    plan = [
        {"time": "10:00", "minutes": 120, "kind": "прогулка"},
        {"time": "12:30", "minutes": 60,  "kind": "обед"},
        {"time": "14:00", "minutes": 90,  "kind": "музей"},
        {"time": "16:00", "minutes": 90,  "kind": "прогулка"},
        {"time": "19:00", "minutes": 90,  "kind": "ужин"},
    ]
    if "Музеи" in wishes:
        plan[3]["kind"] = "музей"
    if "Активно" in wishes:
        plan[2]["kind"] = "прогулка"
    if "Спокойно" in wishes:
        plan[0].update(time="10:30", minutes=90)
        plan[3].update(time="16:30", minutes=60)
    if "Бюджетно" in wishes:
        plan[4]["kind"] = "обед"
    return plan


def fits(place, wishes):
    """Подходит ли место под «с детьми» и «в дождь»."""
    if "С детьми" in wishes and not place["kids"]:
        return False
    if "В дождь" in wishes and not place["rain"]:
        return False
    return True


def pick(places, kind, used, wishes):
    """Свободное место нужного типа. Порядок: нужный тип под пожелания → соседний тип под пожелания
    → нужный тип любой → соседний любой. Для еды пожелания (дети, дождь) не проверяем."""
    free = [p for p in places if p["name"] not in used]
    meal = kind in ("обед", "ужин")
    for k, check in ((kind, True), (OTHER[kind], True), (kind, False), (OTHER[kind], False)):
        for p in free:
            if kind_of(p) == k and (not check or meal or fits(p, wishes)):
                return p
    return None


def build_route(places, days, wishes):
    """Маршрут: список дней, в каждом — пункты {time, minutes, kind, place}.
    places — места города, уже отсортированные RAG-поиском."""
    used = []
    route = []
    for _ in range(days):
        day = []
        for step in day_plan(wishes):
            k = step["kind"]
            place = pick(places, k, used, wishes)
            if not place and k in ("обед", "ужин"):
                place = pick(places, k, [], wishes)   # кафе можно повторить
            if not place:
                continue
            used.append(place["name"])
            label = kind_of(place)
            if label in ("обед", "ужин"):
                label = "ужин" if step["time"] >= "18:00" else "обед"
            day.append({"time": step["time"], "minutes": step["minutes"], "kind": label, "place": place})
        route.append(day)
    return route


def minutes_of(time):
    """«10:30» → 630 минут."""
    return int(time[:2]) * 60 + int(time[3:])


def time_of(minutes):
    """630 минут → «10:30»."""
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def hours(minutes):
    """90 минут → «1,5 ч»."""
    return f"{minutes / 60:g}".replace(".", ",") + " ч"


def why(item, wishes):
    """Текст «Почему в маршруте» для карточки места."""
    text = []
    kind, time, place = item["kind"], item["time"], item["place"]
    if kind == "прогулка" and time < "12:00":
        text.append("Прогулка с утра, пока у всех есть силы.")
    if kind == "прогулка" and time >= "12:00":
        text.append("Прогулка во второй половине дня.")
    if kind == "музей":
        text.append("Музей в середине дня — можно отдохнуть от улицы.")
    if kind == "обед":
        text.append("Удобно пообедать между прогулками.")
    if kind == "ужин":
        text.append("Ресторан для неспешного ужина в конце дня.")
    if place["kids"] and "С детьми" in wishes:
        text.append("Подходит для детей.")
    if place["rain"] and "В дождь" in wishes:
        text.append("Под крышей — подойдёт, если пойдёт дождь.")
    return " ".join(text)
