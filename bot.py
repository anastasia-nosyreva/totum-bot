import asyncio
import csv
import html
import io
import json
import logging
import os
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery, BufferedInputFile,
    InlineKeyboardMarkup, InlineKeyboardButton,
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DEFAULT_UMO_IDS = [(223247422, "Лиля"), (1166936596, "Женя")]

if not BOT_TOKEN:
    raise SystemExit("❌ Не найден BOT_TOKEN. Создай .env с BOT_TOKEN=...")

DB_PATH = Path(__file__).parent / "feedback.db"
LOG_PATH = Path(__file__).parent / "bot.log"
DRAFT_TIMEOUT_MIN = 90
MIN_TEXT_LEN = 30
HEARTBEAT_HOURS = 6

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("totum_bot")

SCHOOL_TEXT = (
    "📚 Закроем пробелы и сделаем знания прочными\n"
    "📈 Повысим успеваемость\n"
    "📝 Подготовим к контрольным и ВПР"
)
OGE_TEXT = (
    "🧩 Разберем все типы заданий ОГЭ — от простых до повышенной сложности\n"
    "🛠 Отработаем алгоритмы решения — чтобы не терять время и баллы на экзамене\n"
    "🧠 Фокус только на нужных темах — изучим только то, что точно пригодится"
)
EGE_TEXT = (
    "✅ Максимальный акцент на экзаменационные темы — разбираем только то, что нужно для экзамена\n"
    "🛠 Отрабатываем алгоритмы решения — всех типов заданий ЕГЭ\n"
    "📋 Обеспечиваем непрерывный контроль за динамикой — отслеживаем прогресс, корректируем маршрут, даём обратную связь родителям"
)
LANG_TEXT = (
    "🎲 Игровые и интерактивные техники — учим через практику, диалоги, движения и визуальные материалы\n"
    "📚 Устраняем пробелы в школьной программе — закрепляем грамматику и лексику\n"
    "🧏 Развиваем ключевые навыки — аудирование, чтение, письмо и разговорная речь"
)
INDIV_TEXT = (
    "📚 Разработаем индивидуальную программу под ребёнка\n"
    "🎯 Работаем над конкретным запросом, делаем знания прочными\n"
    "📈 Видим прогресс после каждого занятия — отслеживаем динамику и корректируем программу"
)

CLASSES_1_11 = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11"]

CATEGORIES = {
    "🌍 Иностранные языки": {
        "type": "language",
        "items": {
            "🇬🇧 Английский язык": ["С нуля (1–2 класс)"] + [f"{c} класс" for c in CLASSES_1_11[2:]],
            "🇨🇳 Китайский язык":  ["С нуля (1–2 класс)"] + [f"{c} класс" for c in CLASSES_1_11[2:]],
        },
    },
    "📚 Школьные предметы": {
        "type": "subject",
        "items": {
            "Русский язык":    CLASSES_1_11,
            "Математика":      CLASSES_1_11,
            "Физика":          ["7", "8", "9", "10", "11"],
            "Информатика":     ["5", "6", "7", "8", "9", "10", "11"],
            "История":         ["5", "6", "7", "8", "9", "10", "11"],
            "Обществознание":  ["9", "10", "11"],
            "Биология":        ["5", "6", "7", "8", "9", "10", "11"],
            "Химия":           ["8", "9", "10", "11"],
            "География":       ["5", "6", "7", "8", "9", "10", "11"],
        },
    },
    "📝 Подготовка к ОГЭ": {
        "type": "simple",
        "prefix": "Подготовка к ОГЭ, ",
        "items": [
            "русский язык", "математика", "физика", "информатика",
            "история", "обществознание", "английский язык",
            "биология", "химия", "география",
        ],
    },
    "🎓 Подготовка к ЕГЭ": {
        "type": "simple",
        "prefix": "Подготовка к ЕГЭ, ",
        "items": [
            "русский язык", "математика", "физика", "информатика",
            "история", "обществознание", "английский язык",
            "биология", "химия", "география",
        ],
    },
    "🎨 Творческая студия": {
        "type": "simple",
        "items": [
            "Арт-студия и каллиграфия (1–2 класс)",
            "Основы рисования", "Дизайн и рисунок",
            "Скетчинг", "Гитара",
        ],
    },
    "🧸 Дошкольное развитие": {
        "type": "simple",
        "items": ["Школа раннего развития (4–5 лет)", "Подготовка к школе"],
    },
    "🧮 Ментальная арифметика": {
        "type": "simple", "items": ["Ментальная арифметика"],
    },
    "🗣 Логопед": {
        "type": "simple", "items": ["Логопед (индивидуально, очно)"],
    },
    "💻 Компьютерные курсы": {
        "type": "simple",
        "items": [
            "Компьютерный старт (1–2 класс)",
            "Компьютерная грамотность (3–4 класс)",
            "Искусственный интеллект и нейросети",
        ],
    },
    "👤 Индивидуально и мини-группы": {
        "type": "custom_input",
        "items": [
            "Индивидуальное занятие очно (80 мин)",
            "Индивидуальное занятие онлайн (80 мин)",
            "Индивидуальное занятие очно (40 мин)",
            "Мини-группа (любой предмет)",
        ],
    },
}

COURSE_ACTIVITIES = {
    "Арт-студия и каллиграфия (1–2 класс)": (
        "Занятие длится 80 минут: 40 минут — каллиграфия, 40 минут — основы рисования.\n"
        "📐 Правильная осанка и положение тела при письме\n"
        "🔠 Каллиграфия с нуля\n"
        "🎨 Основы композиции и цветоведения"
    ),
    "Основы рисования": (
        "🖼 Основы композиции — как расположить объекты на листе\n"
        "🌈 Цветоведение — какие цвета сочетаются, как создавать гармоничные цветовые решения\n"
        "💡 Свет и тень — как работает источник света и как «живёт» тень на рисунке"
    ),
    "Дизайн и рисунок": (
        "📐 Основы композиции и построения — учимся правильно располагать объекты на листе, работать с пропорциями\n"
        "🎨 Цвет и стиль — изучаем цветовые сочетания, учимся создавать выразительные образы\n"
        "✏️ Развитие творческого мышления — работаем над идеей, учимся видеть и создавать красивое"
    ),
    "Скетчинг": (
        "✏️ Основы рисования и наблюдательности — учимся замечать детали, формы, текстуры и светотени\n"
        "🎨 Композиция, цветоведение, светотени — осваиваем с нуля или углубляем знания\n"
        "⏱ Быстрые зарисовки и скетчинг — учимся фиксировать впечатления на бумаге, пробуем разные материалы"
    ),
    "Гитара": (
        "🧠 Начало с практики — учим держать инструмент, ставить аккорды, играть простые ритмы\n"
        "🎵 Развитие чувства ритма и музыкального слуха — настраиваем «внутренний метроном» и связь с инструментом\n"
        "📘 Теория — в лёгком и понятном формате: основные понятия, нотная грамота и музыкальные закономерности"
    ),
    "Школа раннего развития (4–5 лет)": (
        "🗣 Развитие речи — развиваем связную речь, навык задавать вопросы и находить ответы\n"
        "🌍 Окружающий мир — знакомимся с природой, устройством мира через игры и эксперименты\n"
        "🧠 Мышление и математика — считаем, решаем простые задачи, учимся сравнивать и выявлять закономерности"
    ),
    "Подготовка к школе": (
        "➕ Математика — учим считать, решать простые задачи, распознавать и называть геометрические фигуры\n"
        "🔤 Чтение — развиваем навык быстрого и правильного чтения\n"
        "✍️ Письмо — учим писать печатные буквы и цифры аккуратно и разборчиво"
    ),
    "Ментальная арифметика": (
        "➕ Устный и комбинаторный счёт — формируем навык быстрого вычисления в уме\n"
        "🎯 Концентрация внимания — учим сосредотачиваться и не отвлекаться\n"
        "🧩 Память и мышление — развиваем скорость реакции и логические операции"
    ),
    "Логопед (индивидуально, очно)": (
        "🗣 Постановка и автоматизация звуков — учимся говорить правильно\n"
        "🧩 Развитие речи и фонематического слуха — учим различать звуки, строить предложения, пересказывать\n"
        "🧠 Логика, внимание и память — развиваем мышление, усидчивость"
    ),
    "Компьютерный старт (1–2 класс)": (
        "🖥 Устройство компьютера — как он работает, что внутри и зачем нужны основные компоненты\n"
        "⌨️ Работа с клавиатурой и мышью — уверенно, быстро и без ошибок\n"
        "📎 Работа с программами — осваиваем текстовый редактор, презентации, таблицы"
    ),
    "Компьютерная грамотность (3–4 класс)": (
        "💻 Основы программирования — знакомимся с логикой и алгоритмами через простые и увлекательные задачи\n"
        "🎮 Основы создания игр — учимся создавать свои первые игровые проекты\n"
        "🖥 Работа в графических редакторах — осваиваем базовые инструменты для творчества и проектов"
    ),
    "Искусственный интеллект и нейросети": (
        "🤖 Как использовать ИИ в повседневной жизни — какие инструменты помогают нам каждый день\n"
        "🐱 Как компьютер «видит» и распознаёт объекты — знакомимся с компьютерным зрением\n"
        "🗣 Как работают голосовые помощники — разбираемся, как устройства понимают нас и отвечают"
    ),
    "Мини-группа (любой предмет)": (
        "👥 Индивидуальный подход в мини-группе — до 4 человек, внимание каждому\n"
        "📚 Работаем над конкретными запросами — закрываем пробелы, делаем знания прочными\n"
        "📈 Видим прогресс после каждого занятия — отслеживаем динамику и корректируем программу"
    ),
    "Индивидуальное занятие очно (80 мин)": INDIV_TEXT,
    "Индивидуальное занятие онлайн (80 мин)": INDIV_TEXT,
    "Индивидуальное занятие очно (40 мин)": INDIV_TEXT,
}

MONTHS_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня",
              "июля", "августа", "сентября", "октября", "ноября", "декабря"]


def get_activity(course: str, category: str = "") -> str:
    if course in COURSE_ACTIVITIES:
        return COURSE_ACTIVITIES[course]
    if course.startswith("Подготовка к ОГЭ"):
        return OGE_TEXT
    if course.startswith("Подготовка к ЕГЭ"):
        return EGE_TEXT
    if course.startswith("Мини-группа"):
        return COURSE_ACTIVITIES.get("Мини-группа (любой предмет)", INDIV_TEXT)
    if course.startswith("Индивидуальное занятие"):
        return INDIV_TEXT
    if category == "🌍 Иностранные языки":
        return LANG_TEXT
    if category == "📚 Школьные предметы":
        return SCHOOL_TEXT
    return "(уточнить у администратора)"


PRIMERS = {
    "lang": {
        "activity": "Ознакомились с основной информацией о курсе, правилами работы для достижения цели, с педагогом. Разобрали тему урока «Одежда» (Clothes). Выучили 10 новых слов по теме, тренировали фразу «He/She is wearing...». Выполнили письменные задания: подписывали картинки, описывали одежду персонажей.",
        "diagnostics": "На вводном тестировании Алиса набрала 17 баллов из 19, что показывает уровень знаний выше среднего для начала 5-го класса. В целом база хорошая, но есть несколько моментов, которые стоит подтянуть: иногда путается в грамматических конструкциях, не всегда уверенно выбирает между some и any. Устные вопросы понимает, но отвечает коротко. Более заметные улучшения проявятся через 3–4 недели регулярных занятий.",
        "recommendations": "Рекомендуется посещение занятий в групповом формате, их регулярность, а также систематическое выполнение домашних заданий.",
        "materials": "Для обучения необходимо: 2 тетради для домашних работ в клетку, 1 тетрадь для работы в классе, цветные карандаши.",
    },
    "school": {
        "activity": "Ознакомились с основной информацией о курсе, правилами работы для достижения цели, познакомились с педагогом и другими учениками. В рамках занятия с помощью тестирования была проведена диагностика проверки актуального уровня знаний. Разобрали две темы из входного тестирования.",
        "diagnostics": "За вводное тестирование Марисса набрала 6 из 9 баллов, что показывает средний входной уровень знаний. Имеются трудности с темами: «Личные окончания глаголов», «ТСЯ/ТЬСЯ в глаголах», «Корни с чередованиями». На курсе мы изучим последовательно все темы. Первые улучшения будут заметны через 3–4 недели регулярных занятий.",
        "recommendations": "Рекомендуется посещение занятий в групповом формате, а также систематическое выполнение домашних заданий.",
        "materials": "Для обучения необходимо: 2 тетради в клетку, 1 тетрадь для работы в классе, цветные карандаши.",
    },
    "exam": {
        "activity": "Так как занятия в группе стартовали в начале учебного года, Матвей поучаствовал в разборе теоретического занятия по блоку «Социальные отношения» вместе с остальной группой. Помимо этого, была написана входная диагностика для выявления уровня знаний.",
        "diagnostics": "По итогам входного тестирования Матвей набрал 8 из 22 возможных баллов, что говорит о невысоком входном уровне знаний. Затруднения вызвала работа с заданиями второй части. Стоит отметить, что диагностика включала не весь перечень заданий, особенно это касается второй части. При выполнении рекомендаций педагога, систематическом выполнении домашних заданий и выделении времени для самостоятельной работы есть возможность укрепить и систематизировать знания для достижения цели.",
        "recommendations": "Рекомендуется посещение занятий в групповом формате, а также систематическое выполнение домашних заданий.",
        "materials": "Для обучения необходимо: тетрадь в клетку, ручка, простой карандаш.",
    },
    "creative": {
        "activity": "Познакомились с ребятами в группе. Разобрали тему урока — цветовой круг Иттена (основные и составные цвета), попробовали делать цветовые растяжки. Вспомнили, какие цвета относятся к тёплым, какие — к холодным. Повторили, как смешиваются краски. Затем приступили к рисованию пейзажа в выбранном тоне. Тимофей выбрал тёплые цвета.",
        "diagnostics": "Тимофей активно вовлекался в разговор, общался с другими учениками, отвечал на вопросы и сам не стеснялся их задавать. Гуашь даётся Тимофею хорошо, нет страха белого листа, отлично смешивает краски для получения новых оттенков. Нужно больше внимания уделить работе с мелкими деталями. Первые заметные результаты появятся через 3–4 недели регулярных занятий.",
        "recommendations": "Рекомендуется посещение занятий в групповом формате.",
        "materials": "Также можно приобрести для дома альбом (скетчбук), в котором будут отрабатываться навыки и делаться зарисовки.",
    },
    "preschool": {
        "activity": "На занятии по обучению грамоте разобрали понятие «звук», познакомились со звуком О, дали ему характеристику. Выполнили упражнения по развитию звукового анализа и синтеза — находили место нового звука в слове. Звук О соотнесли с буквой, поработали с ней в индивидуальных прописях. На занятии по математике разобрали тему «Свойства предметов. Объединение в группы по признакам», выполнили задания по ориентировке на листе бумаги.",
        "diagnostics": "Результаты показали хорошо сформированный фонематический слух (различение звуков, отсутствие смешения звуков), что важно для дальнейшего обучения грамоте. Также отмечен достаточный уровень самоконтроля. Артур может отличить гласный звук от согласного, дать характеристику звукам. В работе со схемой слова ему нетрудно понять, где он слышит звук.",
        "recommendations": "Рекомендуется посещение занятий в групповом формате и систематическое выполнение домашних заданий.",
        "materials": "Для обучения необходимо: тетради-прописи, простой и цветные карандаши, счётные материалы.",
    },
    "mental": {
        "activity": "Познакомились с ученицей. На вводном занятии познакомились с основами ментальной арифметики: что такое абакус, числа от 0 до 9 на абакусе, как складывать и вычитать на простых примерах. В конце занятия провели рефлексию, учащиеся рассказали, с чем они познакомились, что научились делать.",
        "diagnostics": "Дара проявила высокую мотивацию к новому виду деятельности. Девочка легко понимает визуальные и тактильные инструкции, что критически важно для работы с абакусом. На протяжении всего занятия сохраняла концентрацию и желание выполнять задания.",
        "recommendations": "Рекомендуется посещать занятия в групповой форме.",
        "materials": "На занятия брать ручку, несколько цветных карандашей.",
    },
    "logo": {
        "activity": "Познакомились с ребёнком, провели диагностику речевого развития. Обследовали звукопроизношение, фонематический слух, слоговую структуру слова, лексику и грамматику. Отработали конкретный звук, выполняли артикуляционную гимнастику. Артём старался, чисто произносит простые звуки, требует внимания постановка шипящих.",
        "diagnostics": "Диагностика показала средний уровень речевого развития. Выявлены трудности с постановкой шипящих звуков и фонематическим слухом. Артём хорошо справляется с простыми артикуляционными упражнениями, но требует дополнительной работы над автоматизацией звуков. При регулярных занятиях и выполнении домашних рекомендаций первые улучшения будут заметны через 3–4 недели.",
        "recommendations": "Рекомендуется посещение занятий в индивидуальном формате, 1–2 раза в неделю.",
        "materials": "Для занятий необходимо: зеркало, тетрадь для домашних заданий, тетрадь для работы в классе.",
    },
    "computer": {
        "activity": "Провели вводную диагностику по предмету. Познакомились с ребятами в группе. Разобрали тему «Вводные понятия Python, ООП программирование», а также выстроили примерный план работы в этом учебном году.",
        "diagnostics": "Савва показал, что имеет навыки в программировании, но в своих знаниях ребёнок не уверен. Диагностика показала хорошее владение навыками пользования ПК. Первые заметные улучшения будут через 3–4 недели регулярных занятий.",
        "recommendations": "Рекомендуется посещение занятий в групповом формате.",
        "materials": "Систематическое выполнение домашних заданий.",
    },
    "individual": {
        "activity": "Повторили основные слова и выражения на китайском языке с помощью музыкального интерактива. Полностью выучили текст песни, содержащий базовые способы приветствия. Узнали, как представиться на китайском языке. Вспомнили счёт до 10, особые обозначения жестами каждого числа.",
        "diagnostics": "Диагностика уровня проходила методом устного собеседования на протяжении всего занятия. У Димы хороший входной уровень знаний, учитывая срок обучения и возраст. Знает основные слова и выражения на слух. Необходимо углубиться в изучение фонетики (произношения), а также познакомиться с правилами написания иероглифов. Первые улучшения будут заметны через 3–4 недели.",
        "recommendations": "Рекомендуется систематическое посещение занятий 1 раз в неделю в индивидуальном формате, а также повторение пройденного материала.",
        "materials": "Для обучения необходимо: прописи (крупная клетка 1×1 см), тетрадь для упражнений 12–24 листа, папка с файлами.",
    },
}


def get_primitive(category: str) -> str:
    mapping = {
        "📝 Подготовка к ОГЭ": "exam",
        "🎓 Подготовка к ЕГЭ": "exam",
        "📚 Школьные предметы": "school",
        "🌍 Иностранные языки": "lang",
        "🎨 Творческая студия": "creative",
        "🧸 Дошкольное развитие": "preschool",
        "🧮 Ментальная арифметика": "mental",
        "🗣 Логопед": "logo",
        "💻 Компьютерные курсы": "computer",
        "👤 Индивидуально и мини-группы": "individual",
    }
    return mapping.get(category, "individual")


def get_primer_field(category: str, field: str) -> str:
    primitive = get_primitive(category)
    primer = PRIMERS.get(primitive, PRIMERS["individual"])
    return primer.get(field, primer.get("activity", ""))


def validate_exam_diagnostics(txt: str, course: str) -> list:
    if not ("огэ" in course.lower() or "егэ" in course.lower()):
        return []
    missing = []
    low = txt.lower()
    if not re.search(r"\d+\s*(?:из|/)\s*\d+", txt):
        missing.append("результат в баллах (например «8 из 22»)")
    if not any(w in low for w in ["низк", "средн", "высок"]):
        missing.append("оценка входного уровня (низкий / средний / выше среднего)")
    if not any(w in low for w in ["трудн", "тем", "задан", "пробел", "ошиб"]):
        missing.append("конкретные трудности и темы")
    if not any(w in low for w in ["не весь", "неполн", "не все задан", "не включ"]):
        missing.append("фраза о том, что тестирование включало не весь перечень заданий")
    if not any(w in low for w in ["восполн", "укрепить", "систематизир", "рекомендаций педагога"]):
        missing.append("фраза про восполнение пробелов / работу с рекомендациями педагога")
    return missing


# ================== ХЕЛПЕРЫ ==================
def esc(s):
    return html.escape(str(s or ""))


def format_date(d):
    return f"{d.day} {MONTHS_GEN[d.month - 1]}"


def season_emoji(d=None):
    d = d or datetime.now()
    m = d.month
    if m in (12, 1, 2):
        return "❄️"
    if m in (3, 4, 5):
        return "🌸"
    if m in (6, 7, 8):
        return "☀️"
    return "🍂"


def capitalize_fio(text: str) -> str:
    return " ".join(w[:1].upper() + w[1:] for w in text.split())


def clean_block(text: str) -> str:
    lines = [l.rstrip() for l in (text or "").splitlines()]
    result = []
    prev_empty = False
    for line in lines:
        if not line.strip():
            if not prev_empty:
                result.append("")
            prev_empty = True
        else:
            result.append(line)
            prev_empty = False
    return "\n".join(result).strip()


# ================== БАЗА ДАННЫХ ==================
def db_init():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    try:
        c.execute("PRAGMA table_info(feedback)")
        cols = [r[1] for r in c.fetchall()]
        if cols:
            if "materials" not in cols:
                c.execute("ALTER TABLE feedback ADD COLUMN materials TEXT DEFAULT ''")
            if "self_notes" not in cols:
                c.execute("ALTER TABLE feedback ADD COLUMN self_notes TEXT DEFAULT ''")
            if "is_oral" not in cols:
                c.execute("ALTER TABLE feedback ADD COLUMN is_oral INTEGER DEFAULT 0")
            if "recipient_id" not in cols:
                c.execute("ALTER TABLE feedback ADD COLUMN recipient_id INTEGER DEFAULT 0")
            if "status" not in cols:
                c.execute("ALTER TABLE feedback ADD COLUMN status TEXT DEFAULT 'pending'")
            if "review_comment" not in cols:
                c.execute("ALTER TABLE feedback ADD COLUMN review_comment TEXT DEFAULT ''")
            if "reviewed_at" not in cols:
                c.execute("ALTER TABLE feedback ADD COLUMN reviewed_at TEXT DEFAULT ''")
            if "reviewed_by" not in cols:
                c.execute("ALTER TABLE feedback ADD COLUMN reviewed_by INTEGER DEFAULT 0")
            if "gender" not in cols:
                c.execute("ALTER TABLE feedback ADD COLUMN gender TEXT DEFAULT ''")
            conn.commit()
    except Exception:
        pass

    try:
        c.execute("PRAGMA table_info(umo)")
        cols = [r[1] for r in c.fetchall()]
        if cols and "name" not in cols:
            c.execute("ALTER TABLE umo ADD COLUMN name TEXT DEFAULT ''")
            c.execute("UPDATE umo SET name = 'Лиля' WHERE user_id = 223247422")
            c.execute("UPDATE umo SET name = 'Женя' WHERE user_id = 1166936596")
            conn.commit()
    except Exception:
        pass

    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        registered_at TEXT NOT NULL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        teacher_name TEXT NOT NULL,
        created_at TEXT NOT NULL,
        lesson_date TEXT,
        child TEXT,
        course TEXT,
        activity TEXT,
        diagnostics TEXT,
        recommendations TEXT,
        materials TEXT,
        self_notes TEXT,
        full_text TEXT,
        is_oral INTEGER DEFAULT 0,
        recipient_id INTEGER DEFAULT 0,
        status TEXT DEFAULT 'pending',
        review_comment TEXT DEFAULT '',
        reviewed_at TEXT DEFAULT '',
        reviewed_by INTEGER DEFAULT 0,
        gender TEXT DEFAULT ''
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        text TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS drafts (
        user_id INTEGER PRIMARY KEY,
        state TEXT,
        data TEXT,
        updated_at TEXT NOT NULL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS umo (
        user_id INTEGER PRIMARY KEY,
        name TEXT DEFAULT ''
    )""")
    c.execute("SELECT COUNT(*) FROM umo")
    if c.fetchone()[0] == 0:
        for uid, name in DEFAULT_UMO_IDS:
            c.execute("INSERT OR IGNORE INTO umo (user_id, name) VALUES (?, ?)", (uid, name))
    conn.commit()
    conn.close()


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


def is_umo(user_id: int) -> bool:
    if is_admin(user_id):
        return True
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT 1 FROM umo WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row is not None


def db_get_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None


def db_save_user(user_id, name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users VALUES (?, ?, ?)",
              (user_id, name, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def db_save_feedback(user_id, teacher_name, data, full_text, recipient_id, is_oral=0):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""INSERT INTO feedback
        (user_id, teacher_name, created_at, lesson_date, child, course,
         activity, diagnostics, recommendations, materials, self_notes,
         full_text, is_oral, recipient_id, status, gender)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
        (user_id, teacher_name, datetime.now().isoformat(),
         data.get("date", ""), data.get("child", ""), data.get("course", ""),
         data.get("activity", ""), data.get("diagnostics", ""),
         data.get("recommendations", ""), data.get("materials", ""),
         data.get("self_notes", ""), full_text, is_oral, recipient_id,
         data.get("gender", "")))
    conn.commit()
    fid = c.lastrowid
    conn.close()
    return fid


def db_update_feedback_after_revision(fid, data, full_text):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""UPDATE feedback SET
        lesson_date = ?, child = ?, course = ?,
        activity = ?, diagnostics = ?, recommendations = ?,
        materials = ?, self_notes = ?, full_text = ?, gender = ?,
        status = 'pending', review_comment = '', reviewed_at = '', reviewed_by = 0
        WHERE id = ?""",
        (data.get("date", ""), data.get("child", ""), data.get("course", ""),
         data.get("activity", ""), data.get("diagnostics", ""),
         data.get("recommendations", ""), data.get("materials", ""),
         data.get("self_notes", ""), full_text, data.get("gender", ""),
         fid))
    conn.commit()
    conn.close()


def db_get_feedback_full(fid):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""SELECT id, user_id, teacher_name, created_at, lesson_date, child,
                 course, activity, diagnostics, recommendations, materials,
                 self_notes, full_text, is_oral, recipient_id, status,
                 review_comment, reviewed_at, reviewed_by, gender
                 FROM feedback WHERE id = ?""", (fid,))
    row = c.fetchone()
    conn.close()
    return row


def db_umo_inbox(user_id, only_mine=True):
    """Возвращает список (id, lesson_date, child, course, teacher_name) со status='pending'."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if only_mine:
        c.execute("""SELECT id, lesson_date, child, course, teacher_name
                     FROM feedback
                     WHERE status = 'pending' AND recipient_id = ?
                     ORDER BY id DESC""", (user_id,))
    else:
        c.execute("""SELECT id, lesson_date, child, course, teacher_name
                     FROM feedback
                     WHERE status = 'pending'
                     ORDER BY id DESC""")
    rows = c.fetchall()
    conn.close()
    return rows


def db_umo_archive(user_id, only_mine=True):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if only_mine:
        c.execute("""SELECT id, lesson_date, child, course, teacher_name
                     FROM feedback
                     WHERE status = 'accepted' AND recipient_id = ?
                     ORDER BY id DESC LIMIT 50""", (user_id,))
    else:
        c.execute("""SELECT id, lesson_date, child, course, teacher_name
                     FROM feedback
                     WHERE status = 'accepted'
                     ORDER BY id DESC LIMIT 50""")
    rows = c.fetchall()
    conn.close()
    return rows


def db_mark_accepted(fid, umo_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""UPDATE feedback SET status = 'accepted',
                 reviewed_at = ?, reviewed_by = ? WHERE id = ?""",
              (datetime.now().isoformat(), umo_id, fid))
    conn.commit()
    conn.close()


def db_mark_needs_revision(fid, umo_id, comment):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""UPDATE feedback SET status = 'needs_revision',
                 review_comment = ?, reviewed_at = ?, reviewed_by = ?
                 WHERE id = ?""", (comment, datetime.now().isoformat(), umo_id, fid))
    conn.commit()
    conn.close()


def db_user_history(user_id, limit=15):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""SELECT id, lesson_date, child, course, is_oral FROM feedback
                 WHERE user_id = ? ORDER BY id DESC LIMIT ?""",
              (user_id, limit))
    rows = c.fetchall()
    conn.close()
    return rows


def db_feedback_text(fid):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT full_text FROM feedback WHERE id = ?", (fid,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None


def db_stats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM feedback")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM feedback WHERE status = 'pending'")
    pending = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM feedback WHERE status = 'accepted'")
    accepted = c.fetchone()[0]
    c.execute("SELECT course, COUNT(*) FROM feedback GROUP BY course ORDER BY 2 DESC LIMIT 5")
    top_courses = c.fetchall()
    c.execute("SELECT teacher_name, COUNT(*) FROM feedback GROUP BY user_id ORDER BY 2 DESC LIMIT 5")
    top_teachers = c.fetchall()
    c.execute("SELECT substr(created_at, 1, 7) AS m, COUNT(*) FROM feedback GROUP BY m ORDER BY m DESC LIMIT 6")
    by_month = c.fetchall()
    conn.close()
    return total, pending, accepted, top_courses, top_teachers, by_month


def db_add_note(user_id, text):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO notes (user_id, text, created_at) VALUES (?, ?, ?)",
              (user_id, text, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def db_get_notes(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, text FROM notes WHERE user_id = ? ORDER BY id DESC", (user_id,))
    rows = c.fetchall()
    conn.close()
    return rows


def db_get_note(note_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT text FROM notes WHERE id = ?", (note_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None


def db_delete_note(note_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    conn.commit()
    conn.close()


def db_save_draft(user_id, state_name, data):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO drafts VALUES (?, ?, ?, ?)",
              (user_id, state_name, json.dumps(data, ensure_ascii=False, default=str),
               datetime.now().isoformat()))
    conn.commit()
    conn.close()


def db_get_draft(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT state, data, updated_at FROM drafts WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row if row else None


def db_delete_draft(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM drafts WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def db_all_feedback_for_export():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""SELECT id, created_at, teacher_name, lesson_date, child,
                 course, full_text FROM feedback ORDER BY id DESC""")
    rows = c.fetchall()
    conn.close()
    return rows


def db_get_umo():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id, name FROM umo")
    rows = c.fetchall()
    conn.close()
    return rows


def db_add_umo(user_id: int, name: str = ""):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO umo (user_id, name) VALUES (?, ?)", (user_id, name))
    conn.commit()
    conn.close()


def db_remove_umo(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM umo WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
# ================== КЛАВИАТУРЫ ==================
def main_menu_kb():
    """Меню педагога."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Создать письменную ОС", callback_data="new_written")],
        [InlineKeyboardButton(text="📞 Создать устную ОС", callback_data="new_oral")],
        [InlineKeyboardButton(text="📚 Моя история", callback_data="history")],
        [InlineKeyboardButton(text="📝 Мои заметки", callback_data="notes")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton(text="📖 Памятка", callback_data="memo")],
    ])


def umo_menu_kb(user_id: int):
    """Меню УМО. Если это админ — добавляем кнопку для переключения в режим педагога."""
    rows = [
        [InlineKeyboardButton(text="📥 Входящие", callback_data="umo_inbox")],
        [InlineKeyboardButton(text="📚 Архив", callback_data="umo_archive")],
        [InlineKeyboardButton(text="📊 Статистика центра", callback_data="umo_stats")],
        [InlineKeyboardButton(text="✏️ Я педагог", callback_data="umo_to_teacher")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def umo_menu_from_teacher_kb():
    """Кнопка возврата в УМО-меню, показывается в меню педагога для УМО."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 В режим УМО", callback_data="umo_back")],
    ])


def back_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 В меню", callback_data="menu")]
    ])


def step_kb(with_back=True):
    rows = []
    if with_back:
        rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back")])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def date_kb():
    today = datetime.now()
    yesterday = today - timedelta(days=1)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Сегодня, {format_date(today)}", callback_data="dt:today"),
         InlineKeyboardButton(text=f"Вчера, {format_date(yesterday)}", callback_data="dt:yesterday")],
        [InlineKeyboardButton(text="✏️ Ввести вручную", callback_data="dt:manual")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="menu")],
    ])


def categories_kb(page=0, per_page=6):
    names = list(CATEGORIES.keys())
    start = page * per_page
    end = start + per_page
    chunk = names[start:end]

    rows = []
    for name in chunk:
        idx = names.index(name)
        rows.append([InlineKeyboardButton(text=name, callback_data=f"cat:{idx}")])

    total = (len(names) + per_page - 1) // per_page
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"catpage:{page-1}"))
    nav.append(InlineKeyboardButton(text=f"{page+1}/{total}", callback_data="noop"))
    if end < len(names):
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"catpage:{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def course_items_kb(category: str):
    cfg = CATEGORIES[category]
    rows = []
    if cfg["type"] == "simple" or cfg["type"] == "custom_input":
        items = cfg["items"]
        for i, name in enumerate(items):
            text = name if len(name) <= 60 else name[:57] + "..."
            rows.append([InlineKeyboardButton(text=text, callback_data=f"crs:{i}")])
    else:
        for i, name in enumerate(cfg["items"].keys()):
            rows.append([InlineKeyboardButton(text=name, callback_data=f"subj:{i}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_cats")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def second_level_kb(category: str, subj_idx: int, page=0, per_page=8):
    cfg = CATEGORIES[category]
    subj = list(cfg["items"].keys())[subj_idx]
    classes = cfg["items"][subj]

    start = page * per_page
    end = start + per_page
    chunk = classes[start:end]

    rows = []
    pair = []
    for c in chunk:
        pair.append(InlineKeyboardButton(text=c, callback_data=f"cls:{start + len(pair)}"))
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)

    total = (len(classes) + per_page - 1) // per_page
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"clspage:{subj_idx}:{page-1}"))
    nav.append(InlineKeyboardButton(text=f"{page+1}/{total}", callback_data="noop"))
    if end < len(classes):
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"clspage:{subj_idx}:{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_cat")])
    return InlineKeyboardMarkup(inline_keyboard=rows), subj


def preview_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Дата", callback_data="edit:date"),
         InlineKeyboardButton(text="✏️ ФИО", callback_data="edit:child")],
        [InlineKeyboardButton(text="✏️ Курс", callback_data="edit:course")],
        [InlineKeyboardButton(text="✏️ Что происходило", callback_data="edit:activity")],
        [InlineKeyboardButton(text="✏️ Диагностика", callback_data="edit:diagnostics")],
        [InlineKeyboardButton(text="✏️ Рекомендации", callback_data="edit:recommendations")],
        [InlineKeyboardButton(text="✏️ Материалы", callback_data="edit:materials")],
        [InlineKeyboardButton(text="✏️ Заметки для УМО", callback_data="edit:self_notes")],
        [InlineKeyboardButton(text="📤 Передать в УМО", callback_data="send")],
        [InlineKeyboardButton(text="🔄 Заполнить заново", callback_data="new_written")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="menu")],
    ])


def after_send_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Ещё ребёнок из этой же группы", callback_data="same_lesson")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="menu")],
    ])


def gender_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👦 Мальчик", callback_data="gender:m"),
         InlineKeyboardButton(text="👧 Девочка", callback_data="gender:f")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")],
    ])


def umo_choice_kb():
    rows = []
    for uid, name in db_get_umo():
        label = name if name else str(uid)
        rows.append([InlineKeyboardButton(text=f"👩 {label}", callback_data=f"umosend:{uid}")])
    if len(rows) >= 2:
        rows.append([InlineKeyboardButton(text="👥 Отправить обоим",
                                          callback_data="umosend:all")])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def recommendation_insert_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📌 Групповой формат", callback_data="ins:group")],
        [InlineKeyboardButton(text="📌 Индивидуальный формат", callback_data="ins:indiv")],
        [InlineKeyboardButton(text="📌 Группа + пара индивидуальных", callback_data="ins:mix")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")],
    ])


def materials_insert_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📌 Пустой шаблон «Для обучения необходимо:»",
                              callback_data="ins:materials_empty")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")],
    ])


def self_notes_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Написать заметку", callback_data="selfnotes:write")],
        [InlineKeyboardButton(text="⏭ Пропустить", callback_data="selfnotes:skip")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")],
    ])


def memo_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Письменная ОС", callback_data="memo:written")],
        [InlineKeyboardButton(text="📞 Устная ОС", callback_data="memo:oral")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="menu")],
    ])


def notes_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Мои шаблоны", callback_data="notes:templates")],
        [InlineKeyboardButton(text="📚 Последние 10 ОС", callback_data="notes:last")],
        [InlineKeyboardButton(text="➕ Добавить шаблон", callback_data="notes:add")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="menu")],
    ])


def draft_resume_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▶️ Продолжить", callback_data="draft:continue")],
        [InlineKeyboardButton(text="🆕 Начать заново", callback_data="draft:restart")],
    ])


def timeout_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▶️ Продолжить", callback_data="draft:continue")],
        [InlineKeyboardButton(text="🆕 Начать заново", callback_data="draft:restart")],
    ])


def dx_confirm_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Дописать", callback_data="dx:retry")],
        [InlineKeyboardButton(text="✅ Всё в порядке, дальше", callback_data="dx:continue")],
    ])


def umo_review_kb(fid: int):
    """Кнопки для просмотра ОС в УМО."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Принято", callback_data=f"umo_accept:{fid}")],
        [InlineKeyboardButton(text="⚠️ На доработку", callback_data=f"umo_revise:{fid}")],
        [InlineKeyboardButton(text="🔙 К входящим", callback_data="umo_inbox")],
    ])


def umo_revision_done_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Входящие", callback_data="umo_inbox")],
        [InlineKeyboardButton(text="🏠 В меню УМО", callback_data="umo_menu")],
    ])


# ================== СОСТОЯНИЯ ==================
class OS(StatesGroup):
    name_reg = State()
    date = State()
    child = State()
    gender = State()
    category = State()
    course = State()
    second_level = State()
    custom_course_input = State()
    activity = State()
    diagnostics = State()
    self_notes = State()
    recommendations = State()
    materials = State()
    confirm = State()
    oral_name = State()
    oral_strength = State()
    oral_growth = State()
    oral_recommendation = State()
    note_add = State()
    umo_review_comment = State()


# ================== ПРОМПТЫ ==================
PROMPTS = {
    "date": (
        "📅 <b>1️⃣ Дата урока</b>\n\n"
        "Выбери дату. Если урок был вчера, а ОС пишешь сегодня — "
        "жми «Вчера»."
    ),
    "child": (
        "👶 <b>2️⃣ ФИО ребёнка</b>\n\n"
        "Напиши фамилию и имя в именительном падеже — как в электронном "
        "журнале. Если там указано неверно — указывай реальное ФИО.\n\n"
        "✅ Пример: Иванов Иван\n"
        "❌ Не так: иванов иван, Иванова Ивана, Ваня"
    ),
    "activity": (
        "🎯 <b>4️⃣ Что происходило на занятии?</b>\n\n"
        "<b>Это одна из трёх самых важных частей ОС.</b> Не пиши формально — "
        "ты видел ребёнка и знаешь, что реально было на уроке. Твоя задача — "
        "показать родителю то, что он не мог увидеть сам.\n\n"
        "<b>Опиши:</b>\n"
        "• С кем познакомились (педагог, ученики), какие правила обсудили\n"
        "• Какую тему разобрали\n"
        "• Какие задания выполняли (устно, письменно, игра)\n"
        "• Что у ребёнка получилось\n"
        "• В каком формате была диагностика и на что направлена\n\n"
        "⚠️ Не пиши: оценку поведения ребёнка, имена других детей, "
        "стоимость, расписание, гарантии, здоровье, политику.\n\n"
        "⚠️ <b>Это пример заполнения — НЕ копируй чужие имена и темы.</b> "
        "Пиши про своего ребёнка.\n\n"
        "👉 <b>Пример для этого типа курса</b> (тапни, чтобы раскрыть)"
    ),
    "diagnostics": (
        "🎯 <b>5️⃣ Что показала вводная диагностика?</b>\n\n"
        "<b>Это самая важная часть ОС.</b> Здесь ты работаешь с ожиданиями "
        "родителя — мягко и профессионально.\n\n"
        "<b>Что написать:</b>\n"
        "• Результат диагностики (баллы + что это значит)\n"
        "• Конкретные трудности и пути их решения\n"
        "• Цель, которую озвучил ребёнок (если озвучивал)\n"
        "• Через какой срок будут заметны первые улучшения\n\n"
        "⚠️ <b>НИКОГДА не пиши:</b> «цель нереалистична», «не выйдет», "
        "«невозможно». Ребята копируют эти фразы, потом приходят родители "
        "с претензией.\n\n"
        "✅ <b>Вместо этого:</b> «При выполнении рекомендаций педагога, "
        "систематическом выполнении домашних заданий и выделении времени "
        "для самостоятельной работы есть возможность укрепить и "
        "систематизировать знания для достижения цели.»\n\n"
        "❗️ <b>Про срок.</b> Первые улучшения — через 3–4 недели регулярных "
        "занятий. При низком входном уровне — дольше.\n\n"
        "❗️ <b>Про тестирование.</b> Если тестирование включало не весь "
        "перечень заданий (особенно ОГЭ/ЕГЭ) — отметь это.\n\n"
        "💬 <b>Как переформулировать (не критикуя):</b>\n"
        "❌ «не знает» → ✅ «есть темы, которые стоит подтянуть»\n"
        "❌ «ленивый» → ✅ «рекомендуем систематически выполнять домашние задания»\n"
        "❌ «плохо отвечает» → ✅ «отвечает коротко, будем развивать развёрнутость»\n\n"
        "📖 Это подсказка для ориентировки. <b>Не копируй дословно</b> — "
        "пиши своими словами и подставляй РЕАЛЬНЫЕ баллы, темы и сроки.\n\n"
        "⚠️ <b>Это пример заполнения — НЕ копируй чужие имена и темы.</b>\n\n"
        "👉 <b>Пример для этого типа курса</b> (тапни, чтобы раскрыть)"
    ),
    "self_notes": (
        "📝 <b>Заметки для себя (необязательно)</b>\n\n"
        "Есть что-то, что важно помнить, но не стоит писать родителю? "
        "Например: мотивация, семейный контекст, поведение.\n\n"
        "Эти заметки сохранятся в твоей истории и будут отправлены "
        "специалисту УМО вместе с ОС, но <b>родитель их не увидит</b>.\n\n"
        "Если писать нечего — жми «⏭ Пропустить»."
    ),
            "recommendations": (
        "🎯 <b>6️⃣ Рекомендации по формату</b>\n\n"
        "Здесь напиши, какой формат занятий предпочтителен и о систематичности.\n\n"
        "Как профессионал ты можешь написать: рекомендуется обучение "
        "в группе, индивидуально, онлайн или офлайн, возможно нужно "
        "взять пару онлайн-индивидуальных занятий к групповым.\n\n"
        "<b>Как отвечать:</b>\n"
        "1. Тапни на шаблон ниже → он скопируется.\n"
        "2. Вставь в поле ответа.\n"
        "3. Дополни своими словами.\n"
        "4. Отправь сообщением.\n\n"
        "📋 <b>Шаблон (тапни, чтобы скопировать):</b>\n"
        "<code>Рекомендуется посещение занятий в групповом формате, "
        "их регулярность, а также систематическое выполнение домашних "
        "заданий.</code>\n\n"
        "👉 <b>Пример для этого типа курса</b> (тапни, чтобы раскрыть)"
    ),
            "materials": (
        "🎯 <b>7️⃣ Материалы для занятий</b>\n\n"
        "Здесь напиши, что ребёнку нужно для обучения в центре.\n\n"
        "Список зависит от курса — уточняй под конкретный предмет: "
        "тетради, папки, карандаши, прописи, скетчбук и т.д.\n\n"
        "<b>Как отвечать:</b>\n"
        "1. Тапни на шаблон ниже → он скопируется.\n"
        "2. Вставь в поле ответа.\n"
        "3. Допиши список материалов.\n"
        "4. Отправь сообщением.\n\n"
        "📋 <b>Шаблон (тапни, чтобы скопировать):</b>\n"
        "<code>Для обучения необходимо: </code>\n\n"
        "👉 <b>Пример для этого типа курса</b> (тапни, чтобы раскрыть)"
    ),
}


# ================== ПАМЯТКИ ==================
MEMO_WRITTEN = (
    "📋 <b>Письменная ОС — подробная памятка</b>\n\n"
    "Письменная ОС отправляется родителю, если он ушёл из центра до "
    "окончания урока или не присутствовал. Текст нужно написать в день "
    "урока и направить специалисту УМО.\n\n"
    "ОС состоит из 6 обязательных блоков — строго по порядку.\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "1️⃣ <b>ПРИВЕТСТВИЕ</b>\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "Стандартное приветствие от центра — оно уже заложено в боте, "
    "менять не нужно.\n\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "2️⃣ <b>ЧТО ПРОИСХОДИЛО НА ЗАНЯТИИ</b>\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "Факты без оценки. Родителя на уроке не было — он знает о занятии "
    "только со слов ребёнка (а ребёнок часто говорит «ничего не делали»). "
    "Твоя задача — показать, чем именно вы занимались.\n\n"
    "<b>Что описать:</b>\n"
    "• С кем познакомились (педагог, ученики), какие правила обсудили\n"
    "• Какую тему разобрали\n"
    "• Какие задания выполняли (устно, письменно, игра)\n"
    "• Что у ребёнка получилось\n"
    "• В каком формате была диагностика и на что направлена\n\n"
    "⚠️ <b>Не пиши:</b>\n"
    "• Оценку поведения ребёнка\n"
    "• Имена других детей\n"
    "• Стоимость, расписание, гарантии, здоровье, политику\n\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "3️⃣ <b>ЧТО ПОКАЗАЛА ВВОДНАЯ ДИАГНОСТИКА</b>\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "Это самый важный блок. Здесь ты работаешь с ожиданиями родителя "
    "и даёшь профессиональную картину.\n\n"
    "<b>Что написать:</b>\n"
    "• Результат диагностики (баллы + что это значит)\n"
    "• Конкретные трудности и пути их решения\n"
    "• Цель, которую озвучил ребёнок (если озвучивал)\n"
    "• Через какой срок будут заметны первые улучшения\n\n"
    "⚠️ <b>НИКОГДА не пиши:</b> «цель нереалистична», «не выйдет», "
    "«невозможно». Ребята копируют эти фразы как под копирку — потом "
    "приходят родители с претензией.\n\n"
    "✅ <b>Вместо этого:</b> «При выполнении рекомендаций педагога, "
    "систематическом выполнении домашних заданий и выделении времени "
    "для самостоятельной работы есть возможность укрепить и "
    "систематизировать знания для достижения цели.»\n\n"
    "⏱ <b>Про срок:</b>\n"
    "Первые улучшения — через 3–4 недели регулярных занятий. При низком "
    "входном уровне — дольше. Пиши реальный срок, а не штамп.\n\n"
    "📝 <b>Про тестирование:</b>\n"
    "Если тестирование включало не весь перечень заданий (особенно "
    "ОГЭ/ЕГЭ) — отметь это, чтобы родитель понимал картину целиком.\n\n"
    "💬 <b>Как переформулировать (не критикуя):</b>\n"
    "❌ «не знает» → ✅ «есть темы, которые стоит подтянуть»\n"
    "❌ «ленивый» → ✅ «рекомендуем систематически выполнять домашние задания»\n"
    "❌ «плохо отвечает» → ✅ «отвечает коротко, будем развивать развёрнутость»\n\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "4️⃣ <b>ЧЕМ БУДЕМ ЗАНИМАТЬСЯ НА ЗАНЯТИЯХ</b>\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "Стандартный блок по курсу — он подставляется автоматически, "
    "менять не нужно.\n\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "5️⃣ <b>КАК УЗНАТЬ ПРОГРЕСС</b>\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "Стандартная фраза — тоже подставляется автоматически.\n\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "6️⃣ <b>РЕКОМЕНДАЦИИ</b>\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "<b>Что обязательно указать:</b>\n"
    "• Формат занятий (групповой / индивидуальный / группа + пара индивид.)\n"
    "• Необходимость выполнения домашних заданий\n"
    "• Какие материалы нужны для занятий\n\n"
    "⚠️ Не дублируй фразу про домашку — если уже написал её в блоке "
    "диагностики, здесь не повторяй.\n\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "⚠️ <b>ЧТО ЗАПРЕЩЕНО ОБСУЖДАТЬ С РОДИТЕЛЯМИ</b>\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "• Стоимость курсов, скидки, акции, оплата\n"
    "• Расписание занятий, наличие мест в группах\n"
    "• Конкретные гарантии результата\n"
    "• Лицензии и юридические документы\n"
    "• Сравнение с конкурентами, критика других центров\n"
    "• Критика школьных учителей и школьной программы\n"
    "• Здоровье ребёнка, диагнозы, медицинские рекомендации\n"
    "• Политика, религия, национальность\n"
    "• Личная жизнь педагога, учеников, родителей\n"
    "• Обсуждение других учеников и их успехов\n\n"
    "Если родитель поднимает один из этих вопросов — вежливо "
    "перенаправь к администратору.\n\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "⏰ <b>СРОКИ</b>\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "ОС должна быть у родителя в течение 24 часов с момента окончания "
    "урока.\n\n"
    "<b>Как это работает:</b>\n"
    "• Педагог — готовит ОС в день урока\n"
    "• Специалист УМО — проверяет в день получения\n"
    "• Администратор — отправляет родителю в день получения "
    "проверенного текста"
)


MEMO_ORAL = (
    "📞 <b>Устная ОС — подробная памятка</b>\n\n"
    "Устная ОС даётся родителю лично, если он находится в центре "
    "в момент окончания пробного урока. После беседы педагог "
    "отправляет резюме специалисту УМО.\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "СТРУКТУРА БЕСЕДЫ\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "<b>1. Приветствие и благодарность</b>\n"
    "Представься (если не делал этого раньше), поблагодари родителя "
    "за то, что привёл ребёнка.\n\n"
    "<b>2. Сильные стороны ребёнка</b>\n"
    "Назови 2–3 конкретных факта, которые у ребёнка получились хорошо. "
    "Важно называть ребёнка по имени.\n\n"
    "✅ Пример: «Иван уверенно справился с заданием на тему «Дроби», "
    "хорошо понимает структуру задачи.»\n\n"
    "<b>3. Зоны роста</b>\n"
    "Обозначь 1–2 пробела, которые стоит подтянуть. Говори мягко, без "
    "критики личности, в формате «есть темы, над которыми мы можем "
    "поработать».\n\n"
    "❌ Не говори: «он ничего не знает», «он ленивый», «мне сложно "
    "сказать».\n\n"
    "<b>4. Рекомендация</b>\n"
    "Дай чёткую рекомендацию по курсу и формату занятий.\n\n"
    "✅ Пример: «Я рекомендую Ивану курс по математике в групповом "
    "формате. Мы начнём с темы «Уравнения», затем перейдём к задачам.»\n\n"
    "<b>5. Закрывающий вопрос</b>\n"
    "Закончи вопросом, чтобы вовлечь родителя в диалог.\n\n"
    "✅ Пример: «У вас есть вопросы по тому, как мы будем заниматься "
    "с Иваном?»\n\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "⚠️ <b>ЧТО НЕЛЬЗЯ ГОВОРИТЬ</b>\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "❌ «Он ничего не знает» — звучит безнадёжно, оскорбляет\n"
    "❌ «Он ленивый» — критика личности\n"
    "❌ «В школе плохо учат» — непрофессионально\n"
    "❌ «Мы вас научим за месяц» — необоснованное обещание\n"
    "❌ «Мне сложно сказать» — подрывает доверие\n\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "⚠️ <b>ЧТО НЕЛЬЗЯ ОБСУЖДАТЬ</b>\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "• Стоимость курсов, скидки, акции, оплата\n"
    "• Расписание занятий, наличие мест в группах\n"
    "• Конкретные гарантии результата\n"
    "• Лицензии и юридические документы\n"
    "• Сравнение с конкурентами, критика других центров\n"
    "• Критика школьных учителей и школьной программы\n"
    "• Здоровье ребёнка, диагнозы, медицинские рекомендации\n"
    "• Политика, религия, национальность\n"
    "• Личная жизнь педагога, учеников, родителей\n"
    "• Обсуждение других учеников и их успехов\n\n"
    "Если родитель поднимает один из этих вопросов — вежливо "
    "перенаправь к администратору.\n\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "⏰ <b>СРОКИ</b>\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "Устная ОС считается предоставленной в момент её получения "
    "родителем. После беседы педагог отправляет резюме специалисту УМО.\n\n"
    "Родитель должен получить ОС в течение 24 часов с момента "
    "окончания пробного урока."
)
# ================== БОТ ==================
db_init()
bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

draft_timers: dict = {}


async def notify_admin(text: str):
    try:
        await bot.send_message(ADMIN_ID, f"⚠️ <b>Бот ОС</b>\n\n{text}")
    except Exception as e:
        log.warning(f"Не смог отправить админу: {e}")


async def cancel_draft_timer(user_id: int):
    task = draft_timers.pop(user_id, None)
    if task and not task.done():
        task.cancel()


async def start_draft_timer(user_id: int, chat_id: int):
    await cancel_draft_timer(user_id)

    async def timer():
        try:
            await asyncio.sleep(DRAFT_TIMEOUT_MIN * 60)
            draft = db_get_draft(user_id)
            if not draft:
                return
            state_name, _, _ = draft
            step_names = {
                "OS:date": "Дата урока",
                "OS:child": "ФИО ребёнка",
                "OS:gender": "Пол ребёнка",
                "OS:category": "Выбор категории",
                "OS:course": "Выбор курса",
                "OS:second_level": "Выбор класса",
                "OS:custom_course_input": "Ввод предмета",
                "OS:activity": "Что происходило на занятии",
                "OS:diagnostics": "Что показала диагностика",
                "OS:self_notes": "Заметки для себя",
                "OS:recommendations": "Рекомендации",
                "OS:materials": "Материалы",
                "OS:confirm": "Проверка перед отправкой",
            }
            step = step_names.get(state_name, "заполнение ОС")
            await bot.send_message(
                chat_id,
                f"⏰ Ты остановился на шаге «{step}». "
                f"Заполнение ОС не завершено.\n\nПродолжим?",
                reply_markup=timeout_kb(),
            )
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.exception(f"Ошибка в таймере: {e}")

    draft_timers[user_id] = asyncio.create_task(timer())


async def save_draft(user_id: int, state: FSMContext):
    cur = await state.get_state()
    if not cur:
        return
    data = await state.get_data()
    clean_data = {k: v for k, v in data.items() if not k.startswith("_")}
    db_save_draft(user_id, cur, clean_data)
    await start_draft_timer(user_id, user_id)


async def clear_draft(user_id: int):
    db_delete_draft(user_id)
    await cancel_draft_timer(user_id)


# ================== МЕНЮ ==================
async def show_teacher_menu(target, user_id):
    """Показывает меню педагога. Для УМО добавляет кнопку «в режим УМО»."""
    name = db_get_user(user_id) or "педагог"
    text = (
        f"👋 Привет, <b>{esc(name)}</b>!\n\n"
        "Я помогу собрать обратную связь по пробному уроку "
        "и отправить её ответственному специалисту из УМО. "
        "Пройдём по шагам — в конце получишь готовый текст.\n\n"
        "⏰ Напоминаю: ОС нужно направить специалисту УМО "
        "в день урока. Родитель должен получить её в течение 24 часов.\n\n"
        "Выбери что делаем?"
    )
    kb = main_menu_kb()
    if is_umo(user_id):
        # Добавляем кнопку возврата в УМО
        rows = list(kb.inline_keyboard)
        rows.append([InlineKeyboardButton(text="📥 В режим УМО", callback_data="umo_back")])
        kb = InlineKeyboardMarkup(inline_keyboard=rows)

    if isinstance(target, CallbackQuery):
        try:
            await target.message.edit_text(text, reply_markup=kb)
        except TelegramBadRequest:
            await target.message.answer(text, reply_markup=kb)
    else:
        await target.answer(text, reply_markup=kb)


async def show_umo_menu(target, user_id):
    """Показывает меню УМО."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if is_admin(user_id):
        c.execute("SELECT COUNT(*) FROM feedback WHERE status = 'pending'")
    else:
        c.execute("SELECT COUNT(*) FROM feedback WHERE status = 'pending' AND recipient_id = ?", (user_id,))
    pending_count = c.fetchone()[0]
    conn.close()

    name = db_get_user(user_id) or "специалист"
    text = (
        f"👋 Привет, <b>{esc(name)}</b>!\n\n"
        "Ты в режиме <b>специалиста УМО</b>.\n\n"
        f"📥 Входящих на проверку: <b>{pending_count}</b>\n\n"
        "Выбери что делать:"
    )
    if isinstance(target, CallbackQuery):
        try:
            await target.message.edit_text(text, reply_markup=umo_menu_kb(user_id))
        except TelegramBadRequest:
            await target.message.answer(text, reply_markup=umo_menu_kb(user_id))
    else:
        await target.answer(text, reply_markup=umo_menu_kb(user_id))


# ================== ОБРАБОТКА ОШИБОК ==================
@dp.error()
async def on_error(event):
    try:
        exc = event.exception
        log.exception(f"Ошибка: {exc}")
        await notify_admin(f"Ошибка: {type(exc).__name__}: {exc}")
        update = event.update
        if getattr(update, "message", None):
            await update.message.answer(
                "😔 Что-то пошло не так. Я сообщил об ошибке. "
                "Попробуй ещё раз — /start"
            )
        elif getattr(update, "callback_query", None):
            await update.callback_query.answer("Ошибка, попробуй позже")
    except Exception:
        pass
    return True


# ================== КОМАНДЫ ==================
@dp.message(Command("start"))
async def cmd_start(msg: Message, state: FSMContext):
    await state.clear()
    user_id = msg.from_user.id

    if db_get_user(user_id) is None:
        await msg.answer(
            "Привет!👋\n\n"
            "Я бот для сбора обратной связи по пробным урокам "
            "образовательного центра «Тотум».\n\n"
            "Как тебя зовут? Напиши ФИО — оно будет "
            "подставляться в историю твоих ОС."
        )
        await state.set_state(OS.name_reg)
        return

    # Если УМО — сразу меню УМО
    if is_umo(user_id):
        await show_umo_menu(msg, user_id)
        return

    draft = db_get_draft(user_id)
    if draft:
        _, _, updated = draft
        try:
            dt = datetime.fromisoformat(updated)
            if (datetime.now() - dt).total_seconds() < 24 * 3600:
                await msg.answer(
                    f"📝 У тебя есть незаконченная ОС "
                    f"(последнее действие — {dt.strftime('%d.%m в %H:%M')}).\n\n"
                    f"Продолжить?",
                    reply_markup=draft_resume_kb(),
                )
                return
        except Exception:
            pass
        db_delete_draft(user_id)

    await show_teacher_menu(msg, user_id)


@dp.message(OS.name_reg)
async def step_name_reg(msg: Message, state: FSMContext):
    name = msg.text.strip()
    if len(name) < 2:
        await msg.answer("Слишком коротко. Напиши имя ещё раз.")
        return
    db_save_user(msg.from_user.id, name)
    await state.clear()
    await msg.answer(f"✅ Записал: <b>{esc(name)}</b>")
    if is_umo(msg.from_user.id):
        await show_umo_menu(msg, msg.from_user.id)
    else:
        await show_teacher_menu(msg, msg.from_user.id)


@dp.message(Command("menu"))
async def cmd_menu(msg: Message, state: FSMContext):
    await state.clear()
    if db_get_user(msg.from_user.id) is None:
        await cmd_start(msg, state)
        return
    if is_umo(msg.from_user.id):
        await show_umo_menu(msg, msg.from_user.id)
    else:
        await show_teacher_menu(msg, msg.from_user.id)


@dp.message(Command("cancel"))
async def cmd_cancel(msg: Message, state: FSMContext):
    await state.clear()
    await clear_draft(msg.from_user.id)
    await msg.answer("Отменил.")
    if is_umo(msg.from_user.id):
        await show_umo_menu(msg, msg.from_user.id)
    else:
        await show_teacher_menu(msg, msg.from_user.id)


@dp.message(Command("rename"))
async def cmd_rename(msg: Message, state: FSMContext):
    parts = msg.text.split(maxsplit=1)
    if len(parts) < 2 or len(parts[1].strip()) < 2:
        await msg.answer("Напиши: /rename Иванова Мария Петровна")
        return
    new_name = parts[1].strip()
    db_save_user(msg.from_user.id, new_name)
    await msg.answer(f"✅ Обновил: <b>{esc(new_name)}</b>")


@dp.message(Command("help"))
async def cmd_help(msg: Message):
    await msg.answer(
        "🤖 <b>Как со мной работать</b>\n\n"
        "1. Нажми «📝 Создать письменную ОС» — проведу по шагам и в конце "
        "дам готовый текст.\n\n"
        "2. На каждом шаге есть подсказка — что писать.\n\n"
        "3. В любой момент можно написать /cancel.\n\n"
        "4. Готовый текст — в <code>-блоке. Тапнешь — скопируется.\n\n"
        "5. Команда /rename НовоеИмя — поменять ФИО.\n\n"
        "📞 Устная ОС — если был родитель в центре."
    )


@dp.message(Command("umo"))
async def cmd_umo(msg: Message):
    if not is_admin(msg.from_user.id):
        await msg.answer("Только для администратора.")
        return
    ids = db_get_umo()
    lines = "\n".join(f"• <b>{esc(name)}</b> — <code>{uid}</code>" for uid, name in ids)
    await msg.answer(
        "👥 <b>Список специалистов УМО</b>\n\n" + lines +
        "\n\n<b>Команды:</b>\n"
        "/umo_add ID Имя — добавить\n"
        "/umo_remove ID — удалить"
    )


@dp.message(Command("umo_add"))
async def cmd_umo_add(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    parts = msg.text.split(maxsplit=2)
    if len(parts) < 3:
        await msg.answer("Напиши: /umo_add 123456789 Имя")
        return
    if not parts[1].strip().isdigit():
        await msg.answer("Первый параметр — числовой ID.")
        return
    uid = int(parts[1].strip())
    name = parts[2].strip()
    db_add_umo(uid, name)
    await msg.answer(f"✅ Добавлен: <b>{esc(name)}</b> (<code>{uid}</code>)")


@dp.message(Command("umo_remove"))
async def cmd_umo_remove(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    parts = msg.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().isdigit():
        await msg.answer("Напиши: /umo_remove 123456789")
        return
    uid = int(parts[1].strip())
    db_remove_umo(uid)
    await msg.answer(f"✅ Удалено: <code>{uid}</code>")


@dp.message(Command("export"))
async def cmd_export(msg: Message):
    if not is_admin(msg.from_user.id):
        await msg.answer("Эта команда только для администратора.")
        return
    rows = db_all_feedback_for_export()
    if not rows:
        await msg.answer("ОС пока нет.")
        return
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["ID", "Дата создания", "Педагог", "Дата урока",
                     "Ребёнок", "Курс", "Текст ОС"])
    for r in rows:
        writer.writerow(r)
    data = output.getvalue().encode("utf-8-sig")
    file = BufferedInputFile(data, filename="feedback_export.csv")
    await msg.answer_document(file, caption=f"📦 Всего ОС: {len(rows)}")


# ================== МЕНЮ (callback) ==================
@dp.callback_query(F.data == "menu")
async def cb_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await clear_draft(call.from_user.id)
    if is_umo(call.from_user.id):
        await show_umo_menu(call, call.from_user.id)
    else:
        await show_teacher_menu(call, call.from_user.id)
    await call.answer()


@dp.callback_query(F.data == "noop")
async def cb_noop(call: CallbackQuery):
    await call.answer()


@dp.callback_query(F.data == "umo_menu")
async def cb_umo_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await show_umo_menu(call, call.from_user.id)
    await call.answer()


@dp.callback_query(F.data == "umo_to_teacher")
async def cb_umo_to_teacher(call: CallbackQuery, state: FSMContext):
    """Переключение в режим педагога (для УМО)."""
    await state.clear()
    await show_teacher_menu(call, call.from_user.id)
    await call.answer("Режим педагога")


@dp.callback_query(F.data == "umo_back")
async def cb_umo_back(call: CallbackQuery, state: FSMContext):
    """Возврат в режим УМО."""
    await state.clear()
    await show_umo_menu(call, call.from_user.id)
    await call.answer("Режим УМО")


# ================== УМО: ВХОДЯЩИЕ ==================
@dp.callback_query(F.data == "umo_inbox")
async def cb_umo_inbox(call: CallbackQuery, state: FSMContext):
    await state.clear()
    only_mine = not is_admin(call.from_user.id)
    rows = db_umo_inbox(call.from_user.id, only_mine=only_mine)

    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    if not rows:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 В меню УМО", callback_data="umo_menu")]
        ])
        await call.message.answer("📭 Входящих ОС нет.", reply_markup=kb)
        await call.answer()
        return

    buttons = []
    for fid, lesson_date, child, course, teacher_name in rows:
        text = f"{lesson_date or '?'} — {child or '?'} — {course or '?'}\n   👩 от {teacher_name or '?'}"
        # Telegram не любит длинные кнопки
        short = f"{lesson_date or '?'} · {child or '?'} · от {teacher_name or '?'}"
        if len(short) > 60:
            short = short[:57] + "..."
        buttons.append([InlineKeyboardButton(text=short, callback_data=f"umo_view:{fid}")])
    buttons.append([InlineKeyboardButton(text="🏠 В меню УМО", callback_data="umo_menu")])

    await call.message.answer(
        f"📥 <b>Входящие ОС ({len(rows)})</b>\n\nТапни на любую, чтобы открыть.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await call.answer()


@dp.callback_query(F.data.startswith("umo_view:"))
async def cb_umo_view(call: CallbackQuery):
    fid = int(call.data.split(":", 1)[1])
    row = db_get_feedback_full(fid)
    if not row:
        await call.answer("Не найдено", show_alert=True)
        return

    (fid, user_id, teacher_name, created_at, lesson_date, child,
     course, activity, diagnostics, recommendations, materials,
     self_notes, full_text, is_oral, recipient_id, status,
     review_comment, reviewed_at, reviewed_by, gender) = row

    # Проверяем права: админ видит всё, остальные УМО — только свои
    if not is_admin(call.from_user.id) and recipient_id != call.from_user.id:
        await call.answer("Эта ОС не тебе адресована", show_alert=True)
        return

    header = (
        f"📄 <b>ОС от педагога {esc(teacher_name)}</b>\n\n"
        f"👶 Ребёнок: <b>{esc(child or '')}</b>\n"
        f"📚 Курс: {esc(course or '')}\n"
        f"📅 Дата урока: {esc(lesson_date or '')}\n"
    )

    if self_notes:
        full_text_show = (
            f"{full_text}\n\n"
            "—————————\n\n"
            f"📝 <b>Заметка педагога:</b>\n{esc(self_notes)}"
        )
    else:
        full_text_show = full_text

    # Убираем HTML-теги из full_text для безопасности
    text_clean = full_text_show.replace("<b>", "").replace("</b>", "")

    await call.message.answer(header)
    await call.message.answer(
        f"<code>{esc(text_clean)}</code>",
        reply_markup=umo_review_kb(fid),
    )
    await call.answer()


@dp.callback_query(F.data.startswith("umo_accept:"))
async def cb_umo_accept(call: CallbackQuery):
    fid = int(call.data.split(":", 1)[1])
    row = db_get_feedback_full(fid)
    if not row:
        await call.answer("Не найдено", show_alert=True)
        return

    recipient_id = row[14]
    teacher_id = row[1]
    child = row[5]
    course = row[6]

    if not is_admin(call.from_user.id) and recipient_id != call.from_user.id:
        await call.answer("Эта ОС не тебе адресована", show_alert=True)
        return

    db_mark_accepted(fid, call.from_user.id)

    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await call.message.answer(
        "✅ ОС принята. Она отправлена в Архив.",
        reply_markup=umo_revision_done_kb(),
    )

    # Уведомляем педагога
    try:
        await bot.send_message(
            teacher_id,
            f"✅ <b>Твоя ОС проверена и принята.</b>\n\n"
            f"👶 Ребёнок: <b>{esc(child or '')}</b>\n"
            f"📚 Курс: {esc(course or '')}\n\n"
            "Можешь передавать её родителю.",
        )
    except Exception as e:
        log.warning(f"Не смог уведомить педагога {teacher_id}: {e}")

    await call.answer("Принято")


@dp.callback_query(F.data.startswith("umo_revise:"))
async def cb_umo_revise(call: CallbackQuery, state: FSMContext):
    fid = int(call.data.split(":", 1)[1])
    row = db_get_feedback_full(fid)
    if not row:
        await call.answer("Не найдено", show_alert=True)
        return

    recipient_id = row[14]
    if not is_admin(call.from_user.id) and recipient_id != call.from_user.id:
        await call.answer("Эта ОС не тебе адресована", show_alert=True)
        return

    await state.update_data(_revise_fid=fid)
    await state.set_state(OS.umo_review_comment)

    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await call.message.answer(
        "⚠️ <b>Что нужно доработать?</b>\n\n"
        "Напиши комментарий для педагога — что именно поправить. "
        "Он увидит твой текст и сможет отредактировать ОС.",
    )
    await call.answer()


@dp.message(OS.umo_review_comment)
async def step_umo_review_comment(msg: Message, state: FSMContext):
    comment = clean_block(msg.text or "")
    if len(comment) < 5:
        await msg.answer("Слишком коротко. Напиши хотя бы пару слов, что поправить.")
        return

    data = await state.get_data()
    fid = data.get("_revise_fid")
    if not fid:
        await state.clear()
        await msg.answer("Ошибка, попробуй заново.")
        return

    row = db_get_feedback_full(fid)
    if not row:
        await state.clear()
        await msg.answer("ОС не найдена.")
        return

    teacher_id = row[1]
    child = row[5]
    course = row[6]

    db_mark_needs_revision(fid, msg.from_user.id, comment)

    await state.clear()

    await msg.answer(
        "✅ Комментарий отправлен педагогу. ОС вернётся к нему на доработку.",
        reply_markup=umo_revision_done_kb(),
    )

    # Уведомляем педагога
    try:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Открыть и исправить", callback_data=f"revise_open:{fid}")]
        ])
        await bot.send_message(
            teacher_id,
            f"⚠️ <b>Твоя ОС требует доработки.</b>\n\n"
            f"👶 Ребёнок: <b>{esc(child or '')}</b>\n"
            f"📚 Курс: {esc(course or '')}\n\n"
            f"<b>Что поправить:</b>\n{esc(comment)}",
            reply_markup=kb,
        )
    except Exception as e:
        log.warning(f"Не смог уведомить педагога {teacher_id}: {e}")


# ================== УМО: АРХИВ ==================
@dp.callback_query(F.data == "umo_archive")
async def cb_umo_archive(call: CallbackQuery):
    only_mine = not is_admin(call.from_user.id)
    rows = db_umo_archive(call.from_user.id, only_mine=only_mine)

    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    if not rows:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 В меню УМО", callback_data="umo_menu")]
        ])
        await call.message.answer("📭 Архив пуст.", reply_markup=kb)
        await call.answer()
        return

    buttons = []
    for fid, lesson_date, child, course, teacher_name in rows:
        short = f"{lesson_date or '?'} · {child or '?'} · {course or '?'}"
        if len(short) > 60:
            short = short[:57] + "..."
        buttons.append([InlineKeyboardButton(text=short, callback_data=f"umo_view_arch:{fid}")])
    buttons.append([InlineKeyboardButton(text="🏠 В меню УМО", callback_data="umo_menu")])

    await call.message.answer(
        f"📚 <b>Архив (последние {len(rows)})</b>\n\nПроверенные и принятые ОС.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await call.answer()


@dp.callback_query(F.data.startswith("umo_view_arch:"))
async def cb_umo_view_arch(call: CallbackQuery):
    fid = int(call.data.split(":", 1)[1])
    row = db_get_feedback_full(fid)
    if not row:
        await call.answer("Не найдено", show_alert=True)
        return

    recipient_id = row[14]
    if not is_admin(call.from_user.id) and recipient_id != call.from_user.id:
        await call.answer("Эта ОС не тебе адресована", show_alert=True)
        return

    full_text = row[12]
    self_notes = row[11]
    teacher_name = row[2]
    child = row[5]
    course = row[6]
    lesson_date = row[4]

    header = (
        f"📄 <b>ОС от педагога {esc(teacher_name)}</b>\n\n"
        f"👶 Ребёнок: <b>{esc(child or '')}</b>\n"
        f"📚 Курс: {esc(course or '')}\n"
        f"📅 Дата урока: {esc(lesson_date or '')}\n"
    )

    if self_notes:
        full_text_show = (
            f"{full_text}\n\n"
            "—————————\n\n"
            f"📝 <b>Заметка педагога:</b>\n{esc(self_notes)}"
        )
    else:
        full_text_show = full_text

    text_clean = full_text_show.replace("<b>", "").replace("</b>", "")

    await call.message.answer(header)
    await call.message.answer(f"<code>{esc(text_clean)}</code>")
    await call.answer()


# ================== УМО: СТАТИСТИКА ==================
@dp.callback_query(F.data == "umo_stats")
async def cb_umo_stats(call: CallbackQuery):
    total, pending, accepted, top_courses, top_teachers, by_month = db_stats()

    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    lines = [
        "📊 <b>Статистика центра «Тотум»</b>\n",
        f"📄 Всего ОС: <b>{total}</b>",
        f"📥 На проверке: <b>{pending}</b>",
        f"✅ Принято: <b>{accepted}</b>\n",
    ]

    if by_month:
        lines.append("📅 <b>По месяцам:</b>")
        month_names = ["янв", "фев", "мар", "апр", "май", "июн",
                       "июл", "авг", "сен", "окт", "ноя", "дек"]
        for m, cnt in by_month:
            try:
                y, mm = m.split("-")
                label = f"{month_names[int(mm)-1]} {y}"
            except Exception:
                label = m
            lines.append(f"  • {label}: {cnt}")
        lines.append("")

    if top_courses:
        lines.append("🔥 <b>Популярные курсы:</b>")
        for course, cnt in top_courses:
            lines.append(f"  • {esc(course)} — {cnt}")
        lines.append("")

    if top_teachers:
        lines.append("👩‍🏫 <b>Топ педагогов:</b>")
        for name, cnt in top_teachers:
            lines.append(f"  • {esc(name)} — {cnt}")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 В меню УМО", callback_data="umo_menu")]
    ])
    await call.message.answer("\n".join(lines), reply_markup=kb)
    await call.answer()


# ================== ПЕРЕОТКРЫТИЕ ОС НА ДОРАБОТКУ ==================
@dp.callback_query(F.data.startswith("revise_open:"))
async def cb_revise_open(call: CallbackQuery, state: FSMContext):
    fid = int(call.data.split(":", 1)[1])
    row = db_get_feedback_full(fid)
    if not row:
        await call.answer("ОС не найдена", show_alert=True)
        return

    teacher_id = row[1]
    if teacher_id != call.from_user.id and not is_admin(call.from_user.id):
        await call.answer("Это не твоя ОС", show_alert=True)
        return

    # Восстанавливаем данные в state
    await state.clear()
    await clear_draft(call.from_user.id)

    await state.update_data(
        date=row[4], child=row[5], course=row[6],
        activity=row[7], diagnostics=row[8],
        recommendations=row[9], materials=row[10],
        self_notes=row[11], gender=row[19],
        _revise_fid=fid,  # запомним, что это правка существующей ОС
        _revise_recipient=row[14],  # кому отправить заново
    )

    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await show_preview(call.message, state)
    await call.answer("Открываю ОС для правки")


# ================== НАЗАД ==================
@dp.callback_query(F.data == "back")
async def cb_back(call: CallbackQuery, state: FSMContext):
    cur = await state.get_state()
    data = await state.get_data()

    back_map = {
        "OS:child": None,
        "OS:gender": "child",
        "OS:category": "gender",
        "OS:course": "category",
        "OS:second_level": "category",
        "OS:custom_course_input": "category",
        "OS:activity": "category",
        "OS:diagnostics": "activity",
        "OS:self_notes": "diagnostics",
        "OS:recommendations": "self_notes",
        "OS:materials": "recommendations",
    }
    prev = back_map.get(cur, "menu")

    if prev is None or prev == "menu":
        await state.clear()
        await clear_draft(call.from_user.id)
        if is_umo(call.from_user.id):
            await show_umo_menu(call, call.from_user.id)
        else:
            await show_teacher_menu(call, call.from_user.id)
        await call.answer()
        return

    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    if prev == "date":
        await call.message.answer(PROMPTS["date"], reply_markup=date_kb())
        await state.set_state(OS.date)
    elif prev == "child":
        await call.message.answer(PROMPTS["child"], reply_markup=step_kb())
        await state.set_state(OS.child)
    elif prev == "gender":
        await call.message.answer("👶 <b>Кто ребёнок?</b>", reply_markup=gender_kb())
        await state.set_state(OS.gender)
    elif prev == "category":
        await call.message.answer("3️⃣ Выбери раздел курсов:",
                                  reply_markup=categories_kb())
        await state.set_state(OS.category)
    elif prev == "activity":
        course = data.get("course", "")
        cat = data.get("category", "")
        primer = get_primer_field(cat, "activity")
        await call.message.answer(
            f"Курс: <b>{esc(course)}</b>\n\n" + PROMPTS["activity"]
            + f"\n\n<blockquote>{esc(primer)}</blockquote>",
            reply_markup=step_kb(),
        )
        await state.set_state(OS.activity)
    elif prev == "diagnostics":
        cat = data.get("category", "")
        primer = get_primer_field(cat, "diagnostics")
        await call.message.answer(
            PROMPTS["diagnostics"]
            + f"\n\n<blockquote>{esc(primer)}</blockquote>",
            reply_markup=step_kb(),
        )
        await state.set_state(OS.diagnostics)
    elif prev == "self_notes":
        await call.message.answer(PROMPTS["self_notes"],
                                  reply_markup=self_notes_kb())
        await state.set_state(OS.self_notes)
    elif prev == "recommendations":
        cat = data.get("category", "")
        primer = get_primer_field(cat, "recommendations")
        await call.message.answer(
            PROMPTS["recommendations"]
            + f"\n\n<blockquote>{esc(primer)}</blockquote>",
            reply_markup=recommendation_insert_kb(),
        )
        await state.set_state(OS.recommendations)

    await save_draft(call.from_user.id, state)
    await call.answer()


# ================== ПИСЬМЕННАЯ ОС ==================
@dp.callback_query(F.data == "new_written")
async def cb_new_written(call: CallbackQuery, state: FSMContext):
    if db_get_user(call.from_user.id) is None:
        await call.message.answer("Сначала /start.")
        await call.answer()
        return
    await state.clear()
    await clear_draft(call.from_user.id)
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(PROMPTS["date"], reply_markup=date_kb())
    await state.set_state(OS.date)
    await save_draft(call.from_user.id, state)
    await call.answer()


# --- Дата ---
@dp.callback_query(OS.date, F.data.startswith("dt:"))
async def step_date_btn(call: CallbackQuery, state: FSMContext):
    val = call.data.split(":", 1)[1]
    if val == "manual":
        try:
            await call.message.edit_reply_markup(reply_markup=step_kb(with_back=False))
        except Exception:
            pass
        await call.message.answer("Напиши дату урока (например: 3 сентября)",
                                  reply_markup=step_kb(with_back=False))
        await call.answer()
        return
    d = datetime.now() if val == "today" else datetime.now() - timedelta(days=1)
    await state.update_data(date=format_date(d))
    data = await state.get_data()
    if data.get("editing"):
        await state.update_data(editing=False)
        await save_draft(call.from_user.id, state)
        await show_preview(call.message, state)
    else:
        await call.message.answer(PROMPTS["child"], reply_markup=step_kb())
        await state.set_state(OS.child)
        await save_draft(call.from_user.id, state)
    await call.answer()


@dp.message(OS.date)
async def step_date_text(msg: Message, state: FSMContext):
    await state.update_data(date=msg.text.strip())
    data = await state.get_data()
    if data.get("editing"):
        await state.update_data(editing=False)
        await save_draft(msg.from_user.id, state)
        await show_preview(msg, state)
    else:
        await msg.answer(PROMPTS["child"], reply_markup=step_kb())
        await state.set_state(OS.child)
        await save_draft(msg.from_user.id, state)


# --- ФИО + Пол ---
@dp.message(OS.child)
async def step_child(msg: Message, state: FSMContext):
    raw = msg.text.strip()
    if len(raw) < 3:
        await msg.answer("Слишком коротко. Напиши ФИО ещё раз.")
        return
    clean = capitalize_fio(raw)
    await state.update_data(child=clean)
    await msg.answer("👶 <b>Кто ребёнок?</b>", reply_markup=gender_kb())
    await state.set_state(OS.gender)
    await save_draft(msg.from_user.id, state)


@dp.callback_query(OS.gender, F.data.startswith("gender:"))
async def step_gender(call: CallbackQuery, state: FSMContext):
    val = call.data.split(":", 1)[1]
    await state.update_data(gender=val)
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    data = await state.get_data()
    if data.get("editing"):
        await state.update_data(editing=False)
        await save_draft(call.from_user.id, state)
        await show_preview(call.message, state)
        await call.answer()
        return

    # Если это «Ещё ребёнок из группы» — курс и активность уже заполнены.
    # Пропускаем выбор курса и сразу идём к диагностике.
    if data.get("activity") and data.get("course"):
        cat = data.get("category") or data.get("course_category", "")
        primer = get_primer_field(cat, "diagnostics")
        await call.message.answer(
            f"Курс: <b>{esc(data.get('course', ''))}</b>\n"
            f"Что происходило: <i>скопировано из предыдущей ОС</i>\n\n"
            + PROMPTS["diagnostics"]
            + f"\n\n<blockquote>{esc(primer)}</blockquote>",
            reply_markup=step_kb(),
        )
        await state.set_state(OS.diagnostics)
        await save_draft(call.from_user.id, state)
        await call.answer()
        return

    await call.message.answer("3️⃣ Выбери раздел курсов:", reply_markup=categories_kb())
    await state.set_state(OS.category)
    await save_draft(call.from_user.id, state)
    await call.answer()

# --- Категории ---
@dp.callback_query(OS.category, F.data.startswith("catpage:"))
async def step_cat_page(call: CallbackQuery):
    page = int(call.data.split(":", 1)[1])
    try:
        await call.message.edit_reply_markup(reply_markup=categories_kb(page))
    except Exception:
        pass
    await call.answer()


@dp.callback_query(OS.category, F.data.startswith("cat:"))
async def step_cat_pick(call: CallbackQuery, state: FSMContext):
    idx = int(call.data.split(":", 1)[1])
    category = list(CATEGORIES.keys())[idx]
    await state.update_data(category=category)
    cfg = CATEGORIES[category]
    prompt = f"📂 <b>{esc(category)}</b>\n\n"
    if cfg["type"] == "simple" or cfg["type"] == "custom_input":
        prompt += "Выбери курс:"
    elif cfg["type"] == "language":
        prompt += "Выбери язык:"
    else:
        prompt += "Выбери предмет:"
    try:
        await call.message.edit_text(prompt, reply_markup=course_items_kb(category))
    except Exception:
        await call.message.answer(prompt, reply_markup=course_items_kb(category))
    await state.set_state(OS.course)
    await save_draft(call.from_user.id, state)
    await call.answer()


@dp.callback_query(OS.course, F.data == "back_cats")
async def step_back_cats(call: CallbackQuery, state: FSMContext):
    try:
        await call.message.edit_text("3️⃣ Выбери раздел курсов:",
                                     reply_markup=categories_kb())
    except Exception:
        await call.message.answer("3️⃣ Выбери раздел курсов:",
                                  reply_markup=categories_kb())
    await state.set_state(OS.category)
    await save_draft(call.from_user.id, state)
    await call.answer()


@dp.callback_query(OS.course, F.data.startswith("crs:"))
async def step_simple_pick(call: CallbackQuery, state: FSMContext):
    idx = int(call.data.split(":", 1)[1])
    data = await state.get_data()
    category = data.get("category")
    if not category:
        await call.answer("Что-то не так", show_alert=True)
        return
    cfg = CATEGORIES[category]
    items = cfg["items"]

    if idx >= len(items):
        await call.answer("Не найдено", show_alert=True)
        return

    raw = items[idx]

    if category == "👤 Индивидуально и мини-группы":
        await state.update_data(_base_course=raw)
        try:
            await call.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        if raw.startswith("Мини-группа"):
            await call.message.answer(
                "✏️ <b>Напиши предмет</b>\n\n"
                "Формат: «Математика»\n\n"
                "✅ Пример: Математика\n"
                "✅ Пример: Английский язык",
                reply_markup=step_kb(),
            )
        else:
            await call.message.answer(
                "✏️ <b>Напиши предмет и класс</b>\n\n"
                "Формат: «Математика, 7 класс»\n\n"
                "✅ Пример: Математика, 7 класс\n"
                "✅ Пример: Английский язык, 4 класс",
                reply_markup=step_kb(),
            )
        await state.set_state(OS.custom_course_input)
        await save_draft(call.from_user.id, state)
        await call.answer()
        return

    if category == "📝 Подготовка к ОГЭ":
        full = cfg["prefix"] + raw
    elif category == "🎓 Подготовка к ЕГЭ":
        full = cfg["prefix"] + raw
    else:
        full = raw

    await state.update_data(course=full, course_category=category)
    await _after_course(call.message, state, full)
    await call.answer()


@dp.callback_query(OS.course, F.data.startswith("subj:"))
async def step_subject_pick(call: CallbackQuery, state: FSMContext):
    idx = int(call.data.split(":", 1)[1])
    data = await state.get_data()
    category = data.get("category")
    if not category:
        await call.answer("Что-то не так", show_alert=True)
        return
    await state.update_data(current_subject_idx=idx)
    kb, subj = second_level_kb(category, idx)
    prompt = f"📂 <b>{esc(category)}</b>\n\n<b>{esc(subj)}</b>\n\nВыбери класс:"
    try:
        await call.message.edit_text(prompt, reply_markup=kb)
    except Exception:
        await call.message.answer(prompt, reply_markup=kb)
    await state.set_state(OS.second_level)
    await save_draft(call.from_user.id, state)
    await call.answer()


@dp.callback_query(OS.second_level, F.data == "back_to_cat")
async def step_back_to_cat(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    category = data.get("category")
    cfg = CATEGORIES[category]
    prompt = f"📂 <b>{esc(category)}</b>\n\n"
    if cfg["type"] == "language":
        prompt += "Выбери язык:"
    else:
        prompt += "Выбери предмет:"
    try:
        await call.message.edit_text(prompt, reply_markup=course_items_kb(category))
    except Exception:
        await call.message.answer(prompt, reply_markup=course_items_kb(category))
    await state.set_state(OS.course)
    await save_draft(call.from_user.id, state)
    await call.answer()


@dp.callback_query(OS.second_level, F.data.startswith("clspage:"))
async def step_cls_page(call: CallbackQuery, state: FSMContext):
    _, subj_idx, page = call.data.split(":")
    data = await state.get_data()
    category = data.get("category")
    kb, _ = second_level_kb(category, int(subj_idx), int(page))
    try:
        await call.message.edit_reply_markup(reply_markup=kb)
    except Exception:
        pass
    await call.answer()


@dp.callback_query(OS.second_level, F.data.startswith("cls:"))
async def step_class_pick(call: CallbackQuery, state: FSMContext):
    cls_idx = int(call.data.split(":", 1)[1])
    data = await state.get_data()
    category = data.get("category")
    subj_idx = data.get("current_subject_idx")
    if category is None or subj_idx is None:
        await call.answer("Что-то не так", show_alert=True)
        return
    subj_name = list(CATEGORIES[category]["items"].keys())[subj_idx]
    classes = CATEGORIES[category]["items"][subj_name]
    if cls_idx >= len(classes):
        await call.answer("Не найдено", show_alert=True)
        return
    cls = classes[cls_idx]
    if category == "🌍 Иностранные языки":
        if "С нуля" in cls:
            full = f"{subj_name}, 1–2 класс с нуля"
        else:
            full = f"{subj_name}, {cls}"
    else:
        full = f"{subj_name}, {cls.replace(' класс', '')} класс"
    await state.update_data(course=full, course_category=category)
    await _after_course(call.message, state, full)
    await call.answer()


@dp.message(OS.custom_course_input)
async def step_custom_course(msg: Message, state: FSMContext):
    text = msg.text.strip()
    if len(text) < 2:
        await msg.answer("Слишком коротко. Напиши ещё раз.")
        return
    data = await state.get_data()
    base = data.get("_base_course", "")
    if base.startswith("Мини-группа"):
        full = f"Мини-группа по {text.lower()}"
    else:
        full = f"{text}, индивидуально"
    await state.update_data(course=full)
    await _after_course(msg, state, full)


async def _after_course(target, state: FSMContext, course_full: str):
    data = await state.get_data()
    if data.get("editing"):
        await state.update_data(editing=False)
        user_id = target.from_user.id if hasattr(target, "from_user") else None
        if user_id:
            await save_draft(user_id, state)
        await show_preview(target, state)
    else:
        cat = data.get("category", "")
        primer = get_primer_field(cat, "activity")
        await target.answer(
            f"Курс: <b>{esc(course_full)}</b>\n\n" + PROMPTS["activity"]
            + f"\n\n<blockquote>{esc(primer)}</blockquote>",
            reply_markup=step_kb(),
        )
        await state.set_state(OS.activity)
        if hasattr(target, "from_user"):
            await save_draft(target.from_user.id, state)


# --- Что происходило ---
@dp.message(OS.activity)
async def step_activity(msg: Message, state: FSMContext):
    txt = clean_block(msg.text or "")
    if len(txt) < MIN_TEXT_LEN:
        await msg.answer(
            f"⚠️ Слишком коротко ({len(txt)} симв. из {MIN_TEXT_LEN}). "
            "Родителю важно понять картину — напиши хотя бы 2–3 предложения."
        )
        return
    await state.update_data(activity=txt)
    data = await state.get_data()
    if data.get("editing"):
        await state.update_data(editing=False)
        await save_draft(msg.from_user.id, state)
        await show_preview(msg, state)
        return
    cat = data.get("category", "")
    primer = get_primer_field(cat, "diagnostics")
    await msg.answer(
        PROMPTS["diagnostics"]
        + f"\n\n<blockquote>{esc(primer)}</blockquote>",
        reply_markup=step_kb(),
    )
    await state.set_state(OS.diagnostics)
    await save_draft(msg.from_user.id, state)


# --- Диагностика с валидацией ---
@dp.message(OS.diagnostics)
async def step_diagnostics(msg: Message, state: FSMContext):
    txt = clean_block(msg.text or "")
    if len(txt) < MIN_TEXT_LEN:
        await msg.answer(
            f"⚠️ Слишком коротко ({len(txt)} симв. из {MIN_TEXT_LEN}). "
            "Здесь важна авторская интерпретация — напиши подробнее."
        )
        return

    data = await state.get_data()
    course = data.get("course", "")
    missing = validate_exam_diagnostics(txt, course)

    if missing:
        items = "\n".join(f"• {esc(m)}" for m in missing)
        await msg.answer(
            "⚠️ <b>Для ОГЭ/ЕГЭ в этом блоке не хватает важных деталей:</b>\n\n"
            f"{items}\n\n"
            "Допиши текст и пришли заново — или подтверди, что всё в порядке.",
            reply_markup=dx_confirm_kb(),
        )
        await state.update_data(_pending_diagnostics=txt)
        return

    await state.update_data(diagnostics=txt)
    if data.get("editing"):
        await state.update_data(editing=False)
        await save_draft(msg.from_user.id, state)
        await show_preview(msg, state)
        return
    await msg.answer(PROMPTS["self_notes"], reply_markup=self_notes_kb())
    await state.set_state(OS.self_notes)
    await save_draft(msg.from_user.id, state)


@dp.callback_query(F.data == "dx:retry")
async def cb_dx_retry(call: CallbackQuery, state: FSMContext):
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(
        "Окей, допиши текст и пришли одним сообщением.",
        reply_markup=step_kb(),
    )
    await call.answer()


@dp.callback_query(F.data == "dx:continue")
async def cb_dx_continue(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    txt = data.get("_pending_diagnostics", "")
    if not txt:
        await call.answer("Текст потерялся, отправь заново", show_alert=True)
        return
    await state.update_data(diagnostics=txt, _pending_diagnostics="")
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    if data.get("editing"):
        await state.update_data(editing=False)
        await save_draft(call.from_user.id, state)
        await show_preview(call.message, state)
        await call.answer()
        return
    await call.message.answer(PROMPTS["self_notes"], reply_markup=self_notes_kb())
    await state.set_state(OS.self_notes)
    await save_draft(call.from_user.id, state)
    await call.answer()


# --- Заметки для себя ---
@dp.callback_query(OS.self_notes, F.data == "selfnotes:skip")
async def step_selfnotes_skip(call: CallbackQuery, state: FSMContext):
    await state.update_data(self_notes="")
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    data = await state.get_data()
    if data.get("editing"):
        await state.update_data(editing=False)
        await save_draft(call.from_user.id, state)
        await show_preview(call.message, state)
        await call.answer()
        return
    cat = data.get("category", "")
    primer = get_primer_field(cat, "recommendations")
    await call.message.answer(
        PROMPTS["recommendations"]
        + f"\n\n<blockquote>{esc(primer)}</blockquote>",
        reply_markup=recommendation_insert_kb(),
    )
    await state.set_state(OS.recommendations)
    await save_draft(call.from_user.id, state)
    await call.answer()


@dp.callback_query(OS.self_notes, F.data == "selfnotes:write")
async def step_selfnotes_write(call: CallbackQuery, state: FSMContext):
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(
        "✏️ Напиши заметку для УМО (не для родителя):",
        reply_markup=step_kb(),
    )
    await call.answer()


@dp.message(OS.self_notes)
async def step_selfnotes_text(msg: Message, state: FSMContext):
    await state.update_data(self_notes=clean_block(msg.text))
    data = await state.get_data()
    if data.get("editing"):
        await state.update_data(editing=False)
        await save_draft(msg.from_user.id, state)
        await show_preview(msg, state)
        return
    cat = data.get("category", "")
    primer = get_primer_field(cat, "recommendations")
    await msg.answer(
        PROMPTS["recommendations"]
        + f"\n\n<blockquote>{esc(primer)}</blockquote>",
        reply_markup=recommendation_insert_kb(),
    )
    await state.set_state(OS.recommendations)
    await save_draft(msg.from_user.id, state)


# --- Рекомендации ---
@dp.callback_query(OS.recommendations, F.data.startswith("ins:"))
async def step_insert(call: CallbackQuery, state: FSMContext):
    what = call.data.split(":", 1)[1]
    insert_text = ""
    if what == "group":
        insert_text = ("Рекомендуется посещение занятий в групповом формате, "
                       "их регулярность, а также систематическое выполнение "
                       "домашних заданий.")
    elif what == "indiv":
        insert_text = ("Рекомендуется посещение занятий в индивидуальном "
                       "формате, а также систематическое выполнение "
                       "домашних заданий.")
    elif what == "mix":
        insert_text = ("Рекомендуется посещение занятий в групповом формате, "
                       "а также дополнительно 1–2 индивидуальных занятия в "
                       "месяц для точечной проработки сложных тем.")
    await call.message.answer(
        f"📌 <b>Вставь в ответ ниже</b> (скопируй и отправь сообщением):\n\n"
        f"<code>{esc(insert_text)}</code>",
        reply_markup=recommendation_insert_kb(),
    )
    await call.answer()


@dp.message(OS.recommendations)
async def step_recommendations(msg: Message, state: FSMContext):
    txt = clean_block(msg.text or "")
    if len(txt) < MIN_TEXT_LEN:
        await msg.answer(
            f"⚠️ Слишком коротко ({len(txt)} симв. из {MIN_TEXT_LEN}). "
            "Укажи формат и систематичность."
        )
        return
    await state.update_data(recommendations=txt)
    data = await state.get_data()
    if data.get("editing"):
        await state.update_data(editing=False)
        await save_draft(msg.from_user.id, state)
        await show_preview(msg, state)
        return
    cat = data.get("category", "")
    primer = get_primer_field(cat, "materials")
    await msg.answer(
        PROMPTS["materials"]
        + f"\n\n<blockquote>{esc(primer)}</blockquote>",
        reply_markup=materials_insert_kb(),
    )
    await state.set_state(OS.materials)
    await save_draft(msg.from_user.id, state)


# --- Материалы ---
@dp.callback_query(OS.materials, F.data == "ins:materials_empty")
async def step_materials_empty(call: CallbackQuery, state: FSMContext):
    await call.message.answer(
        "📌 <b>Вставь в ответ ниже и дополни:</b>\n\n"
        "<code>Для обучения необходимо: </code>",
        reply_markup=materials_insert_kb(),
    )
    await call.answer()


@dp.message(OS.materials)
async def step_materials(msg: Message, state: FSMContext):
    txt = clean_block(msg.text or "")
    if len(txt) < 5:
        await msg.answer("Слишком коротко. Напиши хотя бы несколько слов.")
        return
    await state.update_data(materials=txt)
    await state.update_data(editing=False)
    await save_draft(msg.from_user.id, state)
    await show_preview(msg, state)


# --- Превью ---
def build_feedback(data: dict) -> str:
    cat = data.get("course_category") or data.get("category", "")
    activities = get_activity(data.get("course", ""), cat)
    emoji = season_emoji()

    gender = data.get("gender", "")
    if gender == "f":
        verb = "посетила"
    elif gender == "m":
        verb = "посетил"
    else:
        verb = "посетил(а)"

    rec = data.get("recommendations", "")
    materials = data.get("materials", "")

    body = (
        f"Приветствуем Вас! На связи образовательный центр «Тотум»!{emoji}\n\n"
        f"{esc(data.get('date', ''))} {esc(data.get('child', ''))} {verb} "
        f"пробный урок по курсу: «{esc(data.get('course', ''))}».\n\n"
        f"📍<b>Что происходило на занятии?</b>\n{esc(data.get('activity', ''))}\n\n"
        f"📍<b>Что показала вводная диагностика?</b>\n{esc(data.get('diagnostics', ''))}\n\n"
        f"📍<b>Чем будем заниматься на занятиях?</b>\n{esc(activities)}\n\n"
        "📍<b>Можно ли узнать прогресс обучения?</b>\n"
        "Безусловно! У вас будет возможность запросить характеристику "
        "успеваемости от преподавателя на любом этапе курса, написав "
        "администратору.\n\n"
        f"📍<b>Что рекомендуем?</b>\n{esc(rec)}"
    )
    if materials:
        body += f"\n\n{esc(materials)}"
    body += "\n\nВы готовы продолжить обучение?"
    return body


async def show_preview(target, state: FSMContext):
    data = await state.get_data()
    text = build_feedback(data)
    await target.answer(
        "Вот что получилось:\n\n" + text,
        reply_markup=preview_kb(),
    )
    await state.set_state(OS.confirm)


@dp.callback_query(OS.confirm, F.data.startswith("edit:"))
async def cb_edit(call: CallbackQuery, state: FSMContext):
    field = call.data.split(":", 1)[1]
    await state.update_data(editing=True)
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    data = await state.get_data()
    cat = data.get("category", "")

    if field == "course":
        await call.message.answer("3️⃣ Выбери раздел курсов:",
                                  reply_markup=categories_kb())
        await state.set_state(OS.category)
    elif field == "date":
        await call.message.answer(PROMPTS["date"], reply_markup=date_kb())
        await state.set_state(OS.date)
    elif field == "child":
        await call.message.answer(PROMPTS["child"], reply_markup=step_kb())
        await state.set_state(OS.child)
    elif field == "activity":
        primer = get_primer_field(cat, "activity")
        await call.message.answer(
            "✏️ Меняем блок.\n\n" + PROMPTS["activity"]
            + f"\n\n<blockquote>{esc(primer)}</blockquote>",
            reply_markup=step_kb(),
        )
        await state.set_state(OS.activity)
    elif field == "diagnostics":
        primer = get_primer_field(cat, "diagnostics")
        await call.message.answer(
            "✏️ Меняем блок.\n\n" + PROMPTS["diagnostics"]
            + f"\n\n<blockquote>{esc(primer)}</blockquote>",
            reply_markup=step_kb(),
        )
        await state.set_state(OS.diagnostics)
    elif field == "self_notes":
        await call.message.answer(
            "✏️ Меняем блок.\n\n" + PROMPTS["self_notes"],
            reply_markup=self_notes_kb(),
        )
        await state.set_state(OS.self_notes)
    elif field == "recommendations":
        primer = get_primer_field(cat, "recommendations")
        await call.message.answer(
            "✏️ Меняем блок.\n\n" + PROMPTS["recommendations"]
            + f"\n\n<blockquote>{esc(primer)}</blockquote>",
            reply_markup=recommendation_insert_kb(),
        )
        await state.set_state(OS.recommendations)
    elif field == "materials":
        primer = get_primer_field(cat, "materials")
        await call.message.answer(
            "✏️ Меняем блок.\n\n" + PROMPTS["materials"]
            + f"\n\n<blockquote>{esc(primer)}</blockquote>",
            reply_markup=materials_insert_kb(),
        )
        await state.set_state(OS.materials)
    await save_draft(call.from_user.id, state)
    await call.answer()


# --- Отправка в УМО ---
@dp.callback_query(OS.confirm, F.data == "send")
async def cb_send(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()

    teacher_name = db_get_user(call.from_user.id) or "Без имени"
    text = build_feedback(data)
    plain = text.replace("<b>", "").replace("</b>", "")

    await state.update_data(_plain_text=plain, _teacher_name=teacher_name)

    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    # Если это правка после доработки — покажем кому, но без выбора
    if data.get("_revise_fid"):
        recipient_id = data.get("_revise_recipient")
        # Отправляем обратно тому же адресату
        row = db_get_umo()
        recipient_name = next((name for uid, name in row if uid == recipient_id), str(recipient_id))

        await state.update_data(_plain_text=plain, _teacher_name=teacher_name)

        # Обновляем ОС
        fid = data.get("_revise_fid")
        db_update_feedback_after_revision(fid, data, plain)

        # Уведомляем УМО
        try:
            await bot.send_message(
                recipient_id,
                f"📝 <b>Педагог {esc(teacher_name)} доработал ОС.</b>\n\n"
                f"👶 Ребёнок: <b>{esc(data.get('child', ''))}</b>\n"
                f"📚 Курс: {esc(data.get('course', ''))}\n"
                f"📅 Дата урока: {esc(data.get('date', ''))}\n\n"
                "—————————\n\n"
                f"{esc(plain)}",
            )
            await call.message.answer(
                f"✅ ОС доработана и отправлена обратно — <b>{esc(recipient_name)}</b>.",
            )
        except Exception as e:
            await call.message.answer(
                f"❌ Не удалось отправить обратно {esc(recipient_name)}: {e}"
            )

        await state.clear()
        await clear_draft(call.from_user.id)
        await call.message.answer("Что дальше?", reply_markup=main_menu_kb())
        await call.answer("Отправлено")
        return

    # Обычная отправка — выбираем получателя
    umo_list = db_get_umo()
    if not umo_list:
        await call.message.answer("⚠️ Нет ни одного специалиста УМО. Напиши админу.")
        await call.answer()
        return

    await call.message.answer(
        "📄 <b>Готовый текст ОС:</b>\n\n"
        f"<code>{esc(plain)}</code>",
    )
    await call.message.answer(
        "📤 <b>Кому отправить на проверку?</b>",
        reply_markup=umo_choice_kb(),
    )
    await call.answer()


@dp.callback_query(OS.confirm, F.data.startswith("umosend:"))
async def cb_umo_send(call: CallbackQuery, state: FSMContext):
    target = call.data.split(":", 1)[1]
    data = await state.get_data()

    plain = data.get("_plain_text", "")
    teacher_name = data.get("_teacher_name", "Без имени")
    self_notes = data.get("self_notes", "").strip()

    if not plain:
        await call.answer("Ошибка, отправь заново", show_alert=True)
        return

    all_umo = db_get_umo()
    if target == "all":
        recipients = all_umo
    else:
        target_id = int(target)
        recipients = [u for u in all_umo if u[0] == target_id]

    if not recipients:
        await call.answer("Получатель не найден", show_alert=True)
        return

    # Сохраняем — каждому получателю своя запись в БД (чтобы статус независимо)
    for umo_id, umo_name in recipients:
        db_save_feedback(call.from_user.id, teacher_name, data, plain,
                         recipient_id=umo_id, is_oral=0)
    await clear_draft(call.from_user.id)

    # Данные для «Ещё ребёнок»
    await state.update_data(
        _sent=False,
        _last_date=data.get("date"),
        _last_course=data.get("course"),
        _last_course_category=data.get("course_category") or data.get("category"),
        _last_activity=data.get("activity"),
        _last_category=data.get("category"),
    )

    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    statuses = []
    for umo_id, umo_name in recipients:
        name = umo_name or str(umo_id)
        try:
            if self_notes:
                umo_text = (
                    f"📄 <b>ОС от педагога {esc(teacher_name)}</b>\n\n"
                    f"👶 Ребёнок: <b>{esc(data.get('child', ''))}</b>\n"
                    f"📚 Курс: {esc(data.get('course', ''))}\n"
                    f"📅 Дата урока: {esc(data.get('date', ''))}\n\n"
                    "—————————\n\n"
                    f"📝 <b>ЗАМЕТКА ДЛЯ УМО (не для родителя):</b>\n"
                    f"{esc(self_notes)}\n\n"
                    "—————————\n\n"
                    f"📄 <b>ОС ДЛЯ РОДИТЕЛЯ:</b>\n"
                    f"{esc(plain)}"
                )
            else:
                umo_text = (
                    f"📄 <b>ОС от педагога {esc(teacher_name)}</b>\n\n"
                    f"👶 Ребёнок: <b>{esc(data.get('child', ''))}</b>\n"
                    f"📚 Курс: {esc(data.get('course', ''))}\n"
                    f"📅 Дата урока: {esc(data.get('date', ''))}\n\n"
                    "—————————\n\n"
                    f"{esc(plain)}"
                )
            await bot.send_message(umo_id, umo_text)
            statuses.append(f"✅ <b>{esc(name)}</b> — ОС отправлена")
        except Exception as e:
            log.warning(f"Не смог отправить УМО {umo_id} ({name}): {e}")
            statuses.append(
                f"❌ <b>{esc(name)}</b> — не доставлено "
                f"(пусть напишет боту /start)"
            )

    await call.message.answer(
        "📤 <b>Статус отправки:</b>\n\n" + "\n".join(statuses)
    )
    await call.message.answer(
        "На этом уроке и в этой же группе были ещё дети, "
        "которым нужно написать ОС?",
        reply_markup=after_send_kb(),
    )
    await call.answer("Отправлено")


@dp.callback_query(F.data == "same_lesson")
async def cb_same_lesson(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    date = data.get("_last_date")
    course = data.get("_last_course")
    cat = data.get("_last_course_category")
    activity = data.get("_last_activity")

    if not (date and course and activity):
        await call.message.answer("Не получилось восстановить данные. Начни заново.")
        await call.answer()
        return

    await state.clear()
    await state.update_data(
        date=date, course=course, course_category=cat,
        activity=activity, category=cat,
    )
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(
        f"📝 <b>Новая ОС из этого же урока</b>\n\n"
        f"Уже заполнено:\n"
        f"• Дата: {esc(date)}\n"
        f"• Курс: {esc(course)}\n"
        f"• Что происходило: <i>скопировано из предыдущей ОС</i>\n\n"
        f"Осталось заполнить:\n"
        f"👶 <b>2️⃣ ФИО ребёнка</b>\n\n"
        f"Напиши фамилию и имя в именительном падеже.\n\n"
        f"✅ Пример: Иванов Иван",
        reply_markup=step_kb(),
    )
    await state.set_state(OS.child)
    await save_draft(call.from_user.id, state)
    await call.answer()


# ================== УСТНАЯ ОС ==================
@dp.callback_query(F.data == "new_oral")
async def cb_new_oral(call: CallbackQuery, state: FSMContext):
    if db_get_user(call.from_user.id) is None:
        await call.message.answer("Сначала /start.")
        await call.answer()
        return
    await state.clear()
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(
        "📞 <b>Устная ОС</b>\n\n"
        "Эта шпаргалка поможет тебе провести беседу с родителем в центре "
        "и затем передать резюме специалисту УМО.\n\n"
        "👶 <b>Имя ребёнка</b>\n\n"
        "Как зовут ребёнка (в формате «Иванов Иван»)?",
        reply_markup=step_kb(with_back=False),
    )
    await state.set_state(OS.oral_name)
    await call.answer()


@dp.message(OS.oral_name)
async def step_oral_name(msg: Message, state: FSMContext):
    await state.update_data(oral_name=capitalize_fio(msg.text.strip()))
    await msg.answer(
        "💪 <b>Сильные стороны</b>\n\n"
        "Назови 2–3 конкретных факта, которые у ребёнка получились хорошо. "
        "Обязательно используй имя.\n\n"
        "✅ Пример: «Иван уверенно справился с заданием на тему "
        "«Дроби», хорошо понимает структуру задачи.»",
        reply_markup=step_kb(),
    )
    await state.set_state(OS.oral_strength)


@dp.message(OS.oral_strength)
async def step_oral_strength(msg: Message, state: FSMContext):
    await state.update_data(oral_strength=clean_block(msg.text))
    await msg.answer(
        "🌱 <b>Зоны роста</b>\n\n"
        "Назови 1–2 пробела, которые стоит подтянуть. Говори мягко, без "
        "критики личности: «есть темы, над которыми мы можем поработать».\n\n"
        "✅ Пример: «У Ивана есть небольшие пробелы в теме «Уравнения». "
        "Над этим мы можем поработать на занятиях.»",
        reply_markup=step_kb(),
    )
    await state.set_state(OS.oral_growth)


@dp.message(OS.oral_growth)
async def step_oral_growth(msg: Message, state: FSMContext):
    await state.update_data(oral_growth=clean_block(msg.text))
    await msg.answer(
        "🎯 <b>Рекомендация</b>\n\n"
        "Дай чёткую рекомендацию по курсу и формату занятий.\n\n"
        "✅ Пример: «Я рекомендую Ивану курс по математике в групповом "
        "формате. Мы начнём с темы «Уравнения», затем перейдём к задачам.»",
        reply_markup=step_kb(),
    )
    await state.set_state(OS.oral_recommendation)


@dp.message(OS.oral_recommendation)
async def step_oral_recommendation(msg: Message, state: FSMContext):
    await state.update_data(oral_recommendation=clean_block(msg.text))
    data = await state.get_data()

    teacher = db_get_user(msg.from_user.id) or "Педагог"
    child = data.get("oral_name", "")
    now = datetime.now().strftime("%d.%m.%Y %H:%M")

    shpargalka_plain = (
        f"📋 Резюме устной ОС для УМО\n\n"
        f"Кому: {child}\n"
        f"Когда: {now}\n"
        f"Педагог: {teacher}\n\n"
        f"💪 Сильные стороны:\n{data.get('oral_strength', '')}\n\n"
        f"🌱 Зоны роста:\n{data.get('oral_growth', '')}\n\n"
        f"🎯 Рекомендация:\n{data.get('oral_recommendation', '')}\n\n"
        f"❓ Закрывающий вопрос родителю:\n"
        f"«У вас есть вопросы по тому, как мы будем заниматься?»"
    )

    # Сохраняем по одной записи на каждого УМО
    for umo_id, umo_name in db_get_umo():
        db_save_feedback(
            msg.from_user.id, teacher,
            {"date": now, "child": child, "course": "(устная)",
             "activity": data.get("oral_strength", ""),
             "diagnostics": data.get("oral_growth", ""),
             "recommendations": data.get("oral_recommendation", ""),
             "materials": "", "self_notes": "", "gender": ""},
            shpargalka_plain,
            recipient_id=umo_id,
            is_oral=1,
        )

    # Отправляем
    statuses = []
    for umo_id, umo_name in db_get_umo():
        name = umo_name or str(umo_id)
        try:
            await bot.send_message(
                umo_id,
                f"📞 <b>Устная ОС от педагога {esc(teacher)}</b>\n\n"
                f"👶 Ребёнок: <b>{esc(child)}</b>\n"
                f"🕐 Когда: {now}\n\n"
                f"{esc(shpargalka_plain)}"
            )
            statuses.append(f"✅ <b>{esc(name)}</b> — резюме получено")
        except Exception as e:
            log.warning(f"Не смог отправить УМО {umo_id} ({name}): {e}")
            statuses.append(f"❌ <b>{esc(name)}</b> — не доставлено")

    await msg.answer("📤 <b>Статус отправки:</b>\n\n" + "\n".join(statuses))
    await state.clear()
    await msg.answer("Что дальше?", reply_markup=main_menu_kb())


# ================== ИСТОРИЯ ==================
@dp.callback_query(F.data == "history")
async def cb_history(call: CallbackQuery):
    rows = db_user_history(call.from_user.id, limit=15)
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    if not rows:
        await call.message.answer("У тебя пока нет созданных ОС.",
                                  reply_markup=back_menu_kb())
        await call.answer()
        return
    buttons = []
    for fid, lesson_date, child, course, is_oral in rows:
        prefix = "📞 " if is_oral else ""
        text = f"{prefix}{lesson_date or '?'} — {child or '?'} — {course or '?'}"
        if len(text) > 60:
            text = text[:57] + "..."
        buttons.append([InlineKeyboardButton(text=text, callback_data=f"hist:{fid}")])
    buttons.append([InlineKeyboardButton(text="🏠 В меню", callback_data="menu")])
    await call.message.answer(
        f"📚 Твои последние ОС ({len(rows)}):\n\nТапни, чтобы посмотреть полный текст.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await call.answer()


@dp.callback_query(F.data.startswith("hist:"))
async def cb_hist_view(call: CallbackQuery):
    fid = int(call.data.split(":", 1)[1])
    text = db_feedback_text(fid)
    if text is None:
        await call.answer("Не найдено", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 К истории", callback_data="history")]
    ])
    await call.message.answer(
        "Тапни по тексту — скопируется:\n\n"
        f"<code>{esc(text)}</code>",
        reply_markup=kb,
    )
    await call.answer()


# ================== СТАТИСТИКА (педагога) ==================
@dp.callback_query(F.data == "stats")
async def cb_stats(call: CallbackQuery):
    total, pending, accepted, top_courses, top_teachers, by_month = db_stats()
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    lines = [
        f"📊 <b>Всего ОС создано:</b> {total}\n",
        f"📥 На проверке: {pending}",
        f"✅ Принято: {accepted}\n",
    ]
    if by_month:
        lines.append("📅 <b>По месяцам:</b>")
        month_names = ["янв", "фев", "мар", "апр", "май", "июн",
                       "июл", "авг", "сен", "окт", "ноя", "дек"]
        for m, cnt in by_month:
            try:
                y, mm = m.split("-")
                label = f"{month_names[int(mm)-1]} {y}"
            except Exception:
                label = m
            lines.append(f"  • {label}: {cnt}")
        lines.append("")
    if top_courses:
        lines.append("🔥 <b>Популярные курсы:</b>")
        for course, cnt in top_courses:
            lines.append(f"  • {esc(course)} — {cnt}")
        lines.append("")
    if top_teachers:
        lines.append("👩‍🏫 <b>Топ педагогов:</b>")
        for name, cnt in top_teachers:
            lines.append(f"  • {esc(name)} — {cnt}")

    await call.message.answer("\n".join(lines), reply_markup=back_menu_kb())
    await call.answer()


# ================== ЗАМЕТКИ ==================
@dp.callback_query(F.data == "notes")
async def cb_notes(call: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(
        "📝 <b>Мои заметки</b>\n\n"
        "Здесь можно хранить свои шаблоны текстов и быстро находить "
        "свои последние ОС.",
        reply_markup=notes_kb(),
    )
    await call.answer()


@dp.callback_query(F.data == "notes:templates")
async def cb_notes_templates(call: CallbackQuery):
    rows = db_get_notes(call.from_user.id)
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    if not rows:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить шаблон", callback_data="notes:add")],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="menu")],
        ])
        await call.message.answer("У тебя пока нет шаблонов.", reply_markup=kb)
        await call.answer()
        return
    buttons = []
    for nid, text in rows:
        preview = text if len(text) <= 55 else text[:52] + "..."
        preview = preview.replace("\n", " ")
        buttons.append([InlineKeyboardButton(text=preview, callback_data=f"note_view:{nid}")])
    buttons.append([InlineKeyboardButton(text="➕ Добавить шаблон", callback_data="notes:add")])
    buttons.append([InlineKeyboardButton(text="🏠 В меню", callback_data="menu")])
    await call.message.answer("📋 Твои шаблоны:",
                              reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await call.answer()


@dp.callback_query(F.data.startswith("note_view:"))
async def cb_note_view(call: CallbackQuery):
    nid = int(call.data.split(":", 1)[1])
    text = db_get_note(nid)
    if text is None:
        await call.answer("Не найдено", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"note_del:{nid}")],
        [InlineKeyboardButton(text="🔙 К шаблонам", callback_data="notes:templates")],
    ])
    await call.message.answer(
        "Тапни, чтобы скопировать:\n\n"
        f"<code>{esc(text)}</code>",
        reply_markup=kb,
    )
    await call.answer()


@dp.callback_query(F.data.startswith("note_del:"))
async def cb_note_del(call: CallbackQuery):
    nid = int(call.data.split(":", 1)[1])
    db_delete_note(nid)
    await call.answer("Удалено")
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer("Шаблон удалён.",
                              reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                  [InlineKeyboardButton(text="🔙 К шаблонам", callback_data="notes:templates")]
                              ]))


@dp.callback_query(F.data == "notes:add")
async def cb_notes_add(call: CallbackQuery, state: FSMContext):
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(
        "📝 Напиши текст шаблона. Потом сможешь его копировать и вставлять "
        "в любую ОС.\n\n"
        "Например: удачная фраза про диагностику или про рекомендации.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="notes")]
        ]),
    )
    await state.set_state(OS.note_add)
    await call.answer()


@dp.message(OS.note_add)
async def step_note_add(msg: Message, state: FSMContext):
    txt = msg.text.strip()
    if len(txt) < 5:
        await msg.answer("Слишком коротко.")
        return
    db_add_note(msg.from_user.id, txt)
    await state.clear()
    await msg.answer("✅ Шаблон сохранён.",
                     reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                         [InlineKeyboardButton(text="📋 К шаблонам", callback_data="notes:templates")],
                         [InlineKeyboardButton(text="🏠 В меню", callback_data="menu")],
                     ]))


@dp.callback_query(F.data == "notes:last")
async def cb_notes_last(call: CallbackQuery):
    rows = db_user_history(call.from_user.id, limit=10)
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    if not rows:
        await call.message.answer("У тебя пока нет ОС.",
                                  reply_markup=back_menu_kb())
        await call.answer()
        return
    buttons = []
    for fid, lesson_date, child, course, is_oral in rows:
        prefix = "📞 " if is_oral else ""
        text = f"{prefix}{lesson_date or '?'} — {child or '?'} — {course or '?'}"
        if len(text) > 60:
            text = text[:57] + "..."
        buttons.append([InlineKeyboardButton(text=text, callback_data=f"hist:{fid}")])
    buttons.append([InlineKeyboardButton(text="🏠 В меню", callback_data="menu")])
    await call.message.answer(
        "📚 Последние 10 твоих ОС:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await call.answer()


# ================== ПАМЯТКА ==================
@dp.callback_query(F.data == "memo")
async def cb_memo(call: CallbackQuery):
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(
        "📖 <b>Памятка</b>\n\nЧто открыть?",
        reply_markup=memo_kb(),
    )
    await call.answer()


@dp.callback_query(F.data == "memo:written")
async def cb_memo_written(call: CallbackQuery):
    await call.message.answer(MEMO_WRITTEN, reply_markup=back_menu_kb())
    await call.answer()


@dp.callback_query(F.data == "memo:oral")
async def cb_memo_oral(call: CallbackQuery):
    await call.message.answer(MEMO_ORAL, reply_markup=back_menu_kb())
    await call.answer()


# ================== ЧЕРНОВИК ==================
@dp.callback_query(F.data == "draft:continue")
async def cb_draft_continue(call: CallbackQuery, state: FSMContext):
    draft = db_get_draft(call.from_user.id)
    if not draft:
        await call.answer("Черновик не найден", show_alert=True)
        await call.message.answer("Начнём с начала.", reply_markup=main_menu_kb())
        return
    state_name, data_json, _ = draft
    data = json.loads(data_json)
    await state.set_data(data)
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    if state_name == "OS:date":
        await call.message.answer(PROMPTS["date"], reply_markup=date_kb())
        await state.set_state(OS.date)
    elif state_name == "OS:child":
        await call.message.answer(PROMPTS["child"], reply_markup=step_kb())
        await state.set_state(OS.child)
    elif state_name == "OS:gender":
        await call.message.answer("👶 <b>Кто ребёнок?</b>", reply_markup=gender_kb())
        await state.set_state(OS.gender)
    elif state_name in ("OS:category", "OS:course", "OS:second_level", "OS:custom_course_input"):
        await call.message.answer("3️⃣ Выбери раздел курсов:",
                                  reply_markup=categories_kb())
        await state.set_state(OS.category)
    elif state_name == "OS:activity":
        cat = data.get("category", "")
        primer = get_primer_field(cat, "activity")
        await call.message.answer(
            PROMPTS["activity"]
            + f"\n\n<blockquote>{esc(primer)}</blockquote>",
            reply_markup=step_kb(),
        )
        await state.set_state(OS.activity)
    elif state_name == "OS:diagnostics":
        cat = data.get("category", "")
        primer = get_primer_field(cat, "diagnostics")
        await call.message.answer(
            PROMPTS["diagnostics"]
            + f"\n\n<blockquote>{esc(primer)}</blockquote>",
            reply_markup=step_kb(),
        )
        await state.set_state(OS.diagnostics)
    elif state_name == "OS:self_notes":
        await call.message.answer(PROMPTS["self_notes"], reply_markup=self_notes_kb())
        await state.set_state(OS.self_notes)
    elif state_name == "OS:recommendations":
        cat = data.get("category", "")
        primer = get_primer_field(cat, "recommendations")
        await call.message.answer(
            PROMPTS["recommendations"]
            + f"\n\n<blockquote>{esc(primer)}</blockquote>",
            reply_markup=recommendation_insert_kb(),
        )
        await state.set_state(OS.recommendations)
    elif state_name == "OS:materials":
        cat = data.get("category", "")
        primer = get_primer_field(cat, "materials")
        await call.message.answer(
            PROMPTS["materials"]
            + f"\n\n<blockquote>{esc(primer)}</blockquote>",
            reply_markup=materials_insert_kb(),
        )
        await state.set_state(OS.materials)
    elif state_name == "OS:confirm":
        await show_preview(call.message, state)
    else:
        await call.message.answer("Что-то пошло не так. Начнём заново.",
                                  reply_markup=main_menu_kb())
    await call.answer("Продолжаем")


@dp.callback_query(F.data == "draft:restart")
async def cb_draft_restart(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await clear_draft(call.from_user.id)
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    if is_umo(call.from_user.id):
        await show_umo_menu(call, call.from_user.id)
    else:
        await show_teacher_menu(call, call.from_user.id)
    await call.answer("Начинаем заново")


# ================== ЗАПУСК ==================
async def restore_draft_timers():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id FROM drafts")
    rows = c.fetchall()
    conn.close()
    for (uid,) in rows:
        await start_draft_timer(uid, uid)
    log.info(f"Восстановлено таймеров: {len(rows)}")


async def heartbeat():
    await asyncio.sleep(300)
    while True:
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM feedback")
            total = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM drafts")
            drafts = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM users")
            users = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM feedback WHERE status = 'pending'")
            pending = c.fetchone()[0]
            conn.close()

            now = datetime.now().strftime("%d.%m.%Y %H:%M")
            await bot.send_message(
                ADMIN_ID,
                f"✅ <b>Бот ОС жив</b>\n\n"
                f"🕐 {now}\n\n"
                f"👥 Педагогов: {users}\n"
                f"📄 Всего ОС: {total}\n"
                f"📥 На проверке: {pending}\n"
                f"📝 Активных черновиков: {drafts}\n\n"
                f"Следующий отчёт — через {HEARTBEAT_HOURS} ч.",
            )
            log.info("Heartbeat отправлен админу")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning(f"Heartbeat не смог отправиться: {e}")

        await asyncio.sleep(HEARTBEAT_HOURS * 3600)


async def main():
    log.info("Бот запускается...")
    await restore_draft_timers()
    asyncio.create_task(heartbeat())
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Бот остановлен")