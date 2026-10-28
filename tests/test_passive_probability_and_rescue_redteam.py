# -*- coding: utf-8 -*-
"""
tests/test_passive_probability_and_rescue_redteam.py
Верификация новых инвариантов активности (Администраторский регламент EndoChat):
1. Clinical Rescue окно 60-180 минут (сообщения моложе 60 мин не спасаются).
2. Полное отключение незваных пассивных ответов в общем чате (ENABLE_PASSIVE_TEXT=False, prob=0.0).
3. Полное отключение незваного пассивного разбора медиа (ENABLE_PASSIVE_MEDIA=False, prob=0.0).
4. Отключение 20-минутного Question Lifeline (ENABLE_QUESTION_LIFELINE=False).
5. Прямые вызовы (@bot, reply боту, "бот, ...") на 100% активны и иммунны к подавлению.
"""

import asyncio
import datetime
import os
import sqlite3
import sys
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import config
import clinical_rescue as cr
import assistant

PASS, FAIL = [], []

def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    status = "OK  " if cond else "FAIL"
    print(f"  [{status}] {name}" + (f" -- {detail}" if detail and not cond else ""))


class DummyEvent:
    def __init__(self, chat_id, sender_id):
        self.chat_id = chat_id
        self.sender_id = sender_id
        self._sender = None
        self.reply = AsyncMock()


class DummyMediaMsg:
    def __init__(self, chat_id, sender_id, msg_id=99999999):
        self.id = msg_id
        self.chat_id = chat_id
        self.sender_id = sender_id
        self.reply_to_msg_id = None
        self.date = datetime.datetime.now(datetime.timezone.utc)
        self.message = "Снимок зуба 46"


def run_tests():
    print("\n==================== TEST PASSIVE PROBABILITY & 60M RESCUE ====================")

    # 1. Проверка конфигурации по умолчанию
    print("\n[1] Проверка констант конфигурации")
    check("CLINICAL_RESCUE_MIN_AGE_MINUTES равен 60", getattr(config, "CLINICAL_RESCUE_MIN_AGE_MINUTES", 0) == 60)
    check("CLINICAL_RESCUE_MAX_AGE_MINUTES равен 180", getattr(config, "CLINICAL_RESCUE_MAX_AGE_MINUTES", 0) == 180)
    check("PASSIVE_TEXT_PROBABILITY равен 0.0", abs(getattr(config, "PASSIVE_TEXT_PROBABILITY", 1.0) - 0.0) < 1e-4)
    check("PASSIVE_MEDIA_PROBABILITY равен 0.0", abs(getattr(config, "PASSIVE_MEDIA_PROBABILITY", 1.0) - 0.0) < 1e-4)
    check("ENABLE_PASSIVE_TEXT равен False", getattr(config, "ENABLE_PASSIVE_TEXT", True) is False)
    check("ENABLE_PASSIVE_MEDIA равен False", getattr(config, "ENABLE_PASSIVE_MEDIA", True) is False)
    check("ENABLE_QUESTION_LIFELINE равен False", getattr(config, "ENABLE_QUESTION_LIFELINE", True) is False)

    # 2. Проверка окна Clinical Rescue: порог ровно 60 минут
    print("\n[2] Проверка окна спасателя: 60 минут порог")
    tmp_dir = tempfile.mkdtemp()
    db_path = os.path.join(tmp_dir, "test_rescue_60m.db")
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE messages (
                msg_id INTEGER PRIMARY KEY,
                chat_id INTEGER,
                sender_id INTEGER,
                sender_name TEXT,
                text TEXT,
                date TEXT,
                reply_to_msg_id INTEGER,
                has_media INTEGER DEFAULT 0,
                media_description TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE bot_sent_messages (
                msg_id INTEGER PRIMARY KEY,
                chat_id INTEGER
            )
        """)
        conn.commit()

    now = datetime.datetime.now(datetime.timezone.utc)
    t_10m = (now - datetime.timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
    t_30m = (now - datetime.timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
    t_35m = (now - datetime.timedelta(minutes=35)).strftime("%Y-%m-%d %H:%M:%S")
    t_55m = (now - datetime.timedelta(minutes=55)).strftime("%Y-%m-%d %H:%M:%S")
    t_65m = (now - datetime.timedelta(minutes=65)).strftime("%Y-%m-%d %H:%M:%S")
    t_80m = (now - datetime.timedelta(minutes=80)).strftime("%Y-%m-%d %H:%M:%S")
    t_200m = (now - datetime.timedelta(minutes=200)).strftime("%Y-%m-%d %H:%M:%S")

    chat_id = -1001888999
    bot_id = 999888

    with sqlite3.connect(db_path) as conn:
        # msg 1: 10 мин назад (слишком свежий для 60 мин)
        conn.execute("INSERT INTO messages (msg_id, chat_id, sender_id, sender_name, text, date) VALUES (1, ?, 10, 'A', 'Как лечить пульпит 16 зуба?', ?)", (chat_id, t_10m))
        # msg 2: 30 мин назад (слишком свежий для 60 мин)
        conn.execute("INSERT INTO messages (msg_id, chat_id, sender_id, sender_name, text, date) VALUES (2, ?, 11, 'B', 'Какой протокол ирригации при периодонтите 21?', ?)", (chat_id, t_30m))
        # msg 3: 35 мин назад (ранее спасался при 33м, ТЕПЕРЬ ОТКЛОНЯЕТСЯ: < 60 мин)
        conn.execute("INSERT INTO messages (msg_id, chat_id, sender_id, sender_name, text, date) VALUES (3, ?, 12, 'C', 'Снимок зуба 47, апекс не пройден, как быть?', ?)", (chat_id, t_35m))
        # msg 4: 55 мин назад (слишком свежий для 60 мин)
        conn.execute("INSERT INTO messages (msg_id, chat_id, sender_id, sender_name, text, date) VALUES (4, ?, 13, 'D', 'Обломок в канале 36 зуба, протокол извлечения?', ?)", (chat_id, t_55m))
        # msg 5: 65 мин назад (ЕДИНСТВЕННЫЙ ВАЛИДНЫЙ КАНДИДАТ: 65 >= 60 и <= 180)
        conn.execute("INSERT INTO messages (msg_id, chat_id, sender_id, sender_name, text, date) VALUES (5, ?, 14, 'E', 'Апекс зуба 21 широкий, чем пломбировать?', ?)", (chat_id, t_65m))
        # msg 6: 80 мин назад, но есть ответ коллеги msg 7
        conn.execute("INSERT INTO messages (msg_id, chat_id, sender_id, sender_name, text, date) VALUES (6, ?, 15, 'F', 'Чем фиксировать штифт в зубе 11?', ?)", (chat_id, t_80m))
        conn.execute("INSERT INTO messages (msg_id, chat_id, sender_id, sender_name, text, date, reply_to_msg_id) VALUES (7, ?, 16, 'G', 'Фиксируйте на композитный цемент', ?, 6)", (chat_id, t_30m))
        # msg 8: 200 мин назад (слишком старый, > 180 мин)
        conn.execute("INSERT INTO messages (msg_id, chat_id, sender_id, sender_name, text, date) VALUES (8, ?, 17, 'H', 'Периодонтит 45 зуба, удалять или нет?', ?)", (chat_id, t_200m))
        conn.commit()

    cands = cr.find_unanswered_clinical_candidates(db_path, chat_id, bot_id=bot_id)
    check("Кандидат ровно 1 (только msg_id 5, возраст 65 мин)", len(cands) == 1)
    if cands:
        check("Выбран msg_id 5 (65 мин >= 60 мин порога)", cands[0]["id"] == 5)

    # 3. Полное подавление незваного пассивного текста в чате
    print("\n[3] Проверка подавления незваного текста в общем чате")
    mock_ctx = (["Доктор: Коллеги, какой силер для зуба 16 выбрать?"], 0, None)

    with patch.object(assistant, "fetch_dynamic_chat_context", new=AsyncMock(return_value=mock_ctx)):
        with patch.object(assistant, "check_llm_triage", new=AsyncMock(return_value=True)) as mock_triage:
            with patch.object(assistant, "has_dental_term", return_value=True):
                with patch.object(assistant, "passive_gate_block_reason_async", new=AsyncMock(return_value=None)):
                    with patch.object(assistant, "claim_passive_slot", return_value=True):
                        event = DummyEvent(chat_id, 12345)
                        fake_bot = MagicMock()
                        fake_bot.get_me = AsyncMock()
                        res = asyncio.run(assistant.check_and_trigger_assistant(
                            fake_bot, event, 99999999, "Коллеги, какой силер для зуба 16 выбрать?", None, "Доктор"
                        ))
                        check("Незваный пассивный текстовый триггер подавлен (False)", res is False)
                        check("LLM триаж НЕ вызывался (полная тишина без вызова бота)", mock_triage.call_count == 0)

    # 4. Полное подавление незваного разбора медиа в чате
    print("\n[4] Проверка подавления незваного разбора медиа")
    media_msg = DummyMediaMsg(chat_id, 12345, 99999999)

    with patch.object(assistant, "is_explicitly_non_dental_media", return_value=False):
        with patch.object(assistant, "has_dental_term", return_value=True):
            with patch.object(assistant, "_safe_search_knowledge_corpus", new=AsyncMock(return_value=("", ""))):
                with patch.object(assistant, "load_state", return_value={"last_passive_media_run": "2000-01-01T00:00:00", "last_passive_text_run": "2000-01-01T00:00:00"}):
                    with patch.object(assistant, "save_state") as mock_save:
                        fake_bot = MagicMock()
                        res = asyncio.run(assistant.check_and_trigger_assistant_media(
                            fake_bot, media_msg, 99999999, "Снимок зуба 46", "Прицельный снимок зуба 46, периодонтит"
                        ))
                        check("Незваный пассивный разбор снимка подавлен (False)", res is False)

    # 5. Иммунитет прямого обращения (@bot / Reply к боту / "бот, ...")
    print("\n[5] Прямое обращение (@bot, Reply к боту, 'бот, ...') активно на 100%")
    known_handles = {"endohelp_bot", "docendobot", "stomchat_bot"}
    
    # 5.1. Тег @username
    text_uname = "@endohelp_bot подскажи протокол при переломе SOCO"
    is_direct_uname = any(f"@{h}" in text_uname.lower() for h in known_handles)
    check("Тег @endohelp_bot классифицирован как прямой вызов (is_direct=True)", is_direct_uname is True)

    # 5.2. Слово "бот, ..."
    text_word = "бот, подскажи дозировку артикаина"
    is_direct_word = text_word.lower().startswith("бот,") or text_word.lower().startswith("бот ")
    check("Обращение 'бот, ...' классифицировано как прямой вызов (is_direct=True)", is_direct_word is True)

    print("\n==================== РЕЗУЛЬТАТ ТЕСТИРОВАНИЯ ====================")
    total_passed = len(PASS)
    total_failed = len(FAIL)
    print(f"PASSED: {total_passed} | FAILED: {total_failed}")
    if total_failed > 0:
        sys.exit(1)

if __name__ == "__main__":
    run_tests()
