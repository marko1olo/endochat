# -*- coding: utf-8 -*-
"""
Red-Team Inquisitor Test Suite: Anti-Duplication Engine & 45-Day Memory Guardrail
for EndoChat Poll Engine and Storage Subsystem (endo_bot.db).

Verifies:
1. Text normalization and stop-word filtering for clinical dental questions.
2. 4-level duplication detection:
   - Level 1: Exact string match (case/punctuation insensitive, ё->е).
   - Level 2: Substring containment (questions >= 25 chars).
   - Level 3: Token Jaccard similarity (threshold >= 0.55).
   - Level 4: Clinical semantic anchor clusters (torque+implant, Schneider+perforation, broken file+bypass, etc.).
3. Negative tests: diverse clinical questions correctly identified as non-duplicates.
4. Fallback preset pool integrity:
   - Exactly 42 unique endodontic presets (6 per category across all 7 days).
   - All 42 presets strictly conform to Telegram limits and sanitize_poll_payload.
   - Zero internal duplicates in the pool.
5. Dynamic 45-day memory filtering in get_fallback_preset:
   - Never picks a recently used preset if fresh alternatives exist in the category.
6. End-to-end run_pipeline deduplication rejection and retry:
   - Inquisitor LLM candidate matching past poll is rejected and retried with critique.
"""

from __future__ import annotations

import asyncio
import datetime
import os
import sys
import unittest
from typing import Any, Dict, List

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import poll_engine
import poll_storage
from poll_engine import (
    MAX_EXPLANATION_LEN,
    MAX_OPTION_LEN,
    MAX_OPTIONS_COUNT,
    MAX_QUESTION_LEN,
    MIN_OPTIONS_COUNT,
    POLL_FALLBACK_PRESETS,
    PollEngine,
    PollPayload,
    PollType,
    get_fallback_preset,
    sanitize_poll_payload,
)
from poll_storage import is_duplicate_poll, normalize_poll_text
from telethon.extensions import html


class TestPollAntiDupInquisitor(unittest.IsolatedAsyncioTestCase):
    """Inquisitor test suite for poll deduplication and 45-day historical memory in EndoChat."""

    def test_normalize_poll_text(self) -> None:
        """Verifies text normalization: lowercasing, punctuation, and ё->е."""
        raw = "Какова первичная клиническая ТАКТИКА при поломке фрагмента файла в средней трети: изогнутого канала?!"
        norm = normalize_poll_text(raw)
        self.assertEqual(
            norm,
            "какова первичная клиническая тактика при поломке фрагмента файла в средней трети изогнутого канала"
        )
        self.assertIn("е", normalize_poll_text("жёлтый"))
        self.assertNotIn("ё", normalize_poll_text("жёлтый"))

    def test_duplicate_exact_and_punctuation_variation(self) -> None:
        """Level 1: Exact match and punctuation/casing variations."""
        recent_polls = [
            {
                "topic": "Эндодонтия: отлом NiTi инструмента в средней трети",
                "question": "Какова первичная клиническая тактика при поломке фрагмента файла в средней трети изогнутого канала?",
                "created_at": "2026-10-28 14:32:00"
            }
        ]

        # Exact match
        is_dup, reason = is_duplicate_poll(
            question="Какова первичная клиническая тактика при поломке фрагмента файла в средней трети изогнутого канала?",
            topic="Эндодонтия",
            recent_polls=recent_polls
        )
        self.assertTrue(is_dup)
        self.assertIn("Точное совпадение", reason or "")

        # Punctuation & casing variation
        is_dup2, reason2 = is_duplicate_poll(
            question="какова первичная клиническая тактика при поломке фрагмента файла в средней трети изогнутого канала?!",
            topic="эндодонтия",
            recent_polls=recent_polls
        )
        self.assertTrue(is_dup2)

    def test_duplicate_substring_and_jaccard_similarity(self) -> None:
        """Level 2 & 3: Substring containment and high Jaccard token overlap."""
        recent_polls = [
            {
                "topic": "Эндодонтия: отлом NiTi инструмента в средней трети",
                "question": "Какова доказательная первичная тактика при отломе инструмента в средней трети изогнутого канала?",
                "created_at": "2026-10-25 10:00:00"
            }
        ]

        # Substring match (candidate contains long core sentence)
        is_dup, reason = is_duplicate_poll(
            question="Какова доказательная первичная тактика при отломе инструмента в средней трети изогнутого канала у кресла?",
            topic="Эндодонтия",
            recent_polls=recent_polls
        )
        self.assertTrue(is_dup)

        # High Jaccard overlap (> 0.50) with slightly altered wording
        is_dup_jaccard, reason_jaccard = is_duplicate_poll(
            question="Какая тактика врача при поломке NiTi инструмента в средней трети изогнутого канала?",
            topic="Эндодонтия",
            recent_polls=recent_polls,
            threshold=0.50
        )
        self.assertTrue(is_dup_jaccard)

    def test_duplicate_clinical_semantic_anchor_clusters(self) -> None:
        """Level 4: Matching key clinical dilemma pairs (e.g. broken file+bypass, смазанный слой+эдта)."""
        recent_polls = [
            {
                "topic": "Ирригация: удаление смазанного слоя и смывы",
                "question": "Какой раствор является препаратом выбора для удаления смазанного слоя и каков протокол промежуточного смыва?",
                "created_at": "2026-10-20 12:00:00"
            }
        ]

        # Different question syntax, but shares anchor cluster {смазан, слой}
        is_dup, reason = is_duplicate_poll(
            question="Какова тактика эндодонтиста если смазанный слой не удаляется стандартным протоколом промывания?",
            topic="Ирригация корневых каналов",
            recent_polls=recent_polls
        )
        self.assertTrue(is_dup)
        self.assertIn("клинического кластера", reason or "")

    def test_negative_different_clinical_questions(self) -> None:
        """Negative test: Distinct clinical dilemmas must NOT be flagged as duplicates."""
        recent_polls = [
            {
                "topic": "Эндодонтия: отлом NiTi инструмента в средней трети",
                "question": "Какова первичная клиническая тактика при поломке фрагмента файла в средней трети изогнутого канала?",
                "created_at": "2026-10-28 14:32:00"
            },
            {
                "topic": "Эндодонтия: перфорация дна полости зуба",
                "question": "Какова оптимальная тактика изоляции и герметизации дефекта перед обработкой каналов?",
                "created_at": "2026-10-27 14:32:00"
            }
        ]

        # Completely different question in microsurgery
        is_dup, reason = is_duplicate_poll(
            question="Под каким углом к продольной оси корня выполняется доказательная микрохирургическая резекция верхушки?",
            topic="Апикальная микрохирургия",
            recent_polls=recent_polls
        )
        self.assertFalse(is_dup)
        self.assertIsNone(reason)

        # Different question in disinfection
        is_dup2, reason2 = is_duplicate_poll(
            question="Какова правильная доказательная тактика купирования упорной экссудации из канала?",
            topic="Дезинфекция корневых каналов",
            recent_polls=recent_polls
        )
        self.assertFalse(is_dup2)
        self.assertIsNone(reason2)

    def test_fallback_preset_pool_size_and_limits(self) -> None:
        """Proves that POLL_FALLBACK_PRESETS has 42 presets (6 per category) and 100% compliant with limits."""
        self.assertEqual(len(POLL_FALLBACK_PRESETS), 42, f"Expected 42 presets, found {len(POLL_FALLBACK_PRESETS)}")

        categories = {}
        questions_seen = set()
        topics_seen = set()

        for idx, preset in enumerate(POLL_FALLBACK_PRESETS, 1):
            cat = preset["category"]
            categories[cat] = categories.get(cat, 0) + 1

            # Check unique questions & topics
            q = preset["question"]
            t = preset["topic"]
            self.assertNotIn(q, questions_seen, f"Preset #{idx} has duplicate question: '{q}'")
            self.assertNotIn(t, topics_seen, f"Preset #{idx} has duplicate topic: '{t}'")
            questions_seen.add(q)
            topics_seen.add(t)

            # Sanitize and limit validation
            payload = sanitize_poll_payload(preset)
            self.assertIsNotNone(payload, f"Preset #{idx} failed sanitization: {t}")
            assert payload is not None

            # Telegram limits
            q_len = len(html.parse(payload.question)[0])
            self.assertLessEqual(q_len, MAX_QUESTION_LEN, f"Preset #{idx} question exceeds {MAX_QUESTION_LEN}: {q_len}")

            self.assertGreaterEqual(len(payload.options), MIN_OPTIONS_COUNT)
            self.assertLessEqual(len(payload.options), MAX_OPTIONS_COUNT)

            for opt_idx, opt in enumerate(payload.options):
                opt_len = len(html.parse(opt)[0])
                self.assertLessEqual(opt_len, MAX_OPTION_LEN, f"Preset #{idx} option #{opt_idx} exceeds {MAX_OPTION_LEN}: {opt_len}")

            exp_len = len(html.parse(payload.explanation_brief)[0])
            self.assertLessEqual(exp_len, MAX_EXPLANATION_LEN, f"Preset #{idx} brief explanation exceeds {MAX_EXPLANATION_LEN}: {exp_len}")

        # Check exact category balance
        expected_categories = {"endo", "ortho", "surgery", "therapy", "materials_battle", "gnathology", "council"}
        self.assertEqual(set(categories.keys()), expected_categories)
        for cat, count in categories.items():
            self.assertEqual(count, 6, f"Category '{cat}' has {count} presets, expected 6!")

    def test_get_fallback_preset_filters_recent_duplicates(self) -> None:
        """Proves get_fallback_preset never picks a recently used preset if fresh ones are available."""
        all_endo_presets = [p for p in POLL_FALLBACK_PRESETS if p.get("category") == "endo"]
        self.assertEqual(len(all_endo_presets), 6)

        # Mark 5 of the 6 endo presets as recently used in the last 45 days
        used_5 = all_endo_presets[:5]
        target_fresh = all_endo_presets[5]

        recent_polls = [
            {
                "topic": p["topic"],
                "question": p["question"],
                "created_at": f"2026-10-0{i+1} 12:00:00"
            }
            for i, p in enumerate(used_5)
        ]

        # Request a fallback for category endo 10 times in a row
        for _ in range(10):
            selected = get_fallback_preset(category="endo", recent_polls=recent_polls)
            self.assertEqual(
                selected.question,
                target_fresh["question"],
                f"Expected fresh preset '{target_fresh['question']}', but got already used '{selected.question}'!"
            )
            self.assertEqual(selected.source, "fallback")

    async def test_run_pipeline_anti_duplication_guardrail(self) -> None:
        """Proves run_pipeline rejects candidate matching recent poll and retries."""
        dup_question = "Какова первичная клиническая тактика при поломке фрагмента файла в средней трети изогнутого канала?"
        recent_polls = [
            {
                "topic": "Эндодонтия: отлом NiTi инструмента в средней трети",
                "question": dup_question,
                "created_at": "2026-10-28 14:32:00"
            }
        ]

        attempt_counter = 0

        async def mock_inquisitor_llm(prompt: str, status_ctx=None, timeout=None):
            nonlocal attempt_counter
            attempt_counter += 1

            if "poll_triage" in str(status_ctx):
                return type("Resp", (), {"text": '{"is_from_chat": false, "topic": "Эндодонтия", "category": "endo", "format_type": "quiz", "needs_case_intro": true}'})(), None

            if "poll_clinical_review" in str(status_ctx):
                return type("Resp", (), {"text": '{"verdict": "PASS", "defects": []}'})(), None

            # Attempt 1: Return exact duplicate from yesterday
            if attempt_counter == 1:
                dup_json = f'''{{
                    "case_intro": "Клинический случай отлома файла.",
                    "question": "{dup_question}",
                    "options": [
                        "Создание байпаса ручными файлами",
                        "Ультразвуковое расшатывание",
                        "Обтурация до отломка",
                        "Резекция верхушки корня"
                    ],
                    "correct_option_id": 0,
                    "explanation_brief": "Создание байпаса — наименее инвазивный протокол.",
                    "explanation_deep": "Байпас сохраняет анатомию канала и прочность корня без стриппинга.",
                    "discussion_seed_question": "когда останавливаете попытки извлечения?"
                }}'''
                return type("Resp", (), {"text": dup_json})(), None

            # Attempt 2: Return completely fresh, innovative clinical case
            fresh_json = '''{
                "case_intro": "Эндодонтическое лечение моляра с анатомией C-shape.",
                "question": "Какой метод обтурации обеспечивает надежную герметизацию анатомии C-shape?",
                "options": [
                    "Вертикальная горячая конденсация разогретой гуттаперчи с силером",
                    "Холодная латеральная конденсация стандартных гуттаперчевых штифтов",
                    "Метод одного мастер-штифта без гидравлического давления",
                    "Пломбирование цинк-эвгеноловой пастой каналонаполнителем"
                ],
                "correct_option_id": 0,
                "explanation_brief": "Горячая вертикальная конденсация трехмерно заполняет перешейки C-shape.",
                "explanation_deep": "Анатомия C-shape характеризуется щелевидными анастомозами, требующими пластичной гуттаперчи.",
                "discussion_seed_question": "какой протокол пломбирования выбираете при анатомии C-shape?"
            }'''
            return type("Resp", (), {"text": fresh_json})(), None

        engine = PollEngine(default_llm_caller=mock_inquisitor_llm)
        payload, media = await engine.run_pipeline(
            chat_context=None,
            now=datetime.datetime(2026, 9, 21, 14, 0, 0),  # Понедельник (Эндодонтия)
            recent_polls=recent_polls
        )

        # Proves that attempt 1 was rejected by deduplicator and attempt 2 was accepted
        self.assertIsNotNone(payload)
        self.assertNotEqual(payload.question, dup_question, "Pipeline must NOT accept the duplicate question!")
        self.assertEqual(payload.question, "Какой метод обтурации обеспечивает надежную герметизацию анатомии C-shape?")
        self.assertEqual(payload.source, "llm")
        self.assertGreaterEqual(attempt_counter, 2, "Deduplication guardrail must have triggered a retry on attempt 1!")


if __name__ == "__main__":
    unittest.main()
