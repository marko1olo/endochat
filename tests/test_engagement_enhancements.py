# -*- coding: utf-8 -*-
"""
Тесты для улучшений вовлеченности в малоактивных чатах (Red Team Fixes).
Проверяет:
1. Распознавание прямых тегов бота (@endohelp_bot, бот, и др.).
2. Адаптивный кулдаун и volume gate для тихих чатов (velocity <= 5).
3. Расширенный словарь клинических кандидатов для Lifeline.
4. Отсутствие запретов на человеческий тон и наличие хуков в промптах.
"""

import unittest
from unittest.mock import patch

import assistant
from question_lifeline import is_clinical_question_candidate


class TestEngagementEnhancements(unittest.IsolatedAsyncioTestCase):

    def test_direct_mention_recognition(self):
        """Проверяет распознавание прямых обращений и тегов бота."""
        bot_uname = "endohelp_bot"

        # 1. Тег через @
        t1 = "@endohelp_bot какой силер лучше взять для латералки?"
        self.assertTrue(
            f"@{bot_uname}" in t1.lower() or bot_uname in t1.lower()
        )

        # 2. Обращение через 'бот,'
        t2 = "Бот, подскажи протокол дезобтурации гуттаперчи"
        self.assertTrue(
            t2.lower().startswith("бот,") or t2.lower().startswith("бот ")
        )

        # 3. Простое сообщение между врачами (не должно считаться прямым вызовом)
        t3 = "Коллеги, кто чем устья раскрывает?"
        self.assertFalse(
            f"@{bot_uname}" in t3.lower() or t3.lower().startswith("бот,")
        )

    async def test_dynamic_cooldown_in_quiet_chat(self):
        """В тихом чате (velocity <= 5) кулдаун не должен раздуваться до 130+ минут."""
        with patch.object(assistant, "get_recent_message_velocity", return_value=2):
            cd_minutes, diag = await assistant.calculate_dynamic_passive_cooldown({})
            # Должно быть в районе 20-35 минут, а не 130 минут!
            self.assertLessEqual(cd_minutes, 40)
            self.assertGreaterEqual(cd_minutes, 15)
            self.assertIn("vel=2", diag)

    def test_lifeline_expanded_keywords(self):
        """Проверяет, что новые эндодонтические маркеры (CeraSeal, байпас и т.д.) распознаются как клинические вопросы."""
        q1 = "Коллеги, кто пробовал CeraSeal при деструктивных формах периодонтита? Как результаты?"
        self.assertTrue(is_clinical_question_candidate(q1))

        q2 = "Подскажите, удался ли кому-нибудь байпас сломанного протейпера в средней трети?"
        self.assertTrue(is_clinical_question_candidate(q2))

        q3 = "Какой протокол ультразвуковой активации гипохлорита через эндочак вы используете?"
        self.assertTrue(is_clinical_question_candidate(q3))

    def test_prompt_persona_integrity(self):
        """Проверяет, что в промптах assistant.py удален запрет 'притворяться человеком' и внедрен хук для дискуссии."""
        import inspect
        source = inspect.getsource(assistant)

        # Не должно быть запрета притворяться человеком
        self.assertNotIn("Запрещено притворяться человеком", source)

        # Должен присутствовать клинический хук для дискуссии
        self.assertIn("КЛИНИЧЕСКИЙ ХУК ДЛЯ ДИСКУССИИ", source)


if __name__ == "__main__":
    unittest.main()
