# -*- coding: utf-8 -*-
"""
tests/test_chairside_tools.py — Полный набор регрессионных тестов для chairside_tools.py.
"""

import sys
import os
import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock

# Ensure endochat root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import chairside_tools as ct


class TestChairsideTools(unittest.TestCase):

    # ─────────────────────────────────────────────────────────────
    # 1. ЗУБНАЯ ФОРМУЛА FDI 11-48
    # ─────────────────────────────────────────────────────────────
    def test_fdi_teeth_anatomy_lookup(self):
        t16 = ct.get_tooth_anatomy(16)
        self.assertIsNotNone(t16)
        self.assertEqual(t16.fdi, 16)
        self.assertIn("MB2", t16.mb2_or_extra_prob)
        self.assertIn("strip perforation", t16.danger_zone)

        t46 = ct.get_tooth_anatomy(46)
        self.assertIsNotNone(t46)
        self.assertEqual(t46.fdi, 46)
        self.assertIn("DANGER ZONE", t46.danger_zone)
        self.assertIn("Middle Mesial", t46.mb2_or_extra_prob)

        t31 = ct.get_tooth_anatomy(31)
        self.assertIsNotNone(t31)
        self.assertEqual(t31.fdi, 31)
        self.assertIn("ЯЗЫЧНЫЙ", t31.danger_zone)

        self.assertIsNone(ct.get_tooth_anatomy(99))

    def test_format_tooth_card(self):
        t26 = ct.get_tooth_anatomy(26)
        card = ct.format_tooth_card(t26)
        self.assertIn("Зуб 26", card)
        self.assertIn("Средняя длина:", card)
        self.assertIn("DANGER ZONE", card)
        self.assertIn("Окклюзионный эндо-доступ:", card)

    # ─────────────────────────────────────────────────────────────
    # 2. КАТАЛОГ СИСТЕМ ФАЙЛОВ: ТОРК И RPM
    # ─────────────────────────────────────────────────────────────
    def test_file_catalog_lookup(self):
        pt = ct.lookup_file_system("protaper")
        self.assertIsNotNone(pt)
        self.assertEqual(pt["system_name"], "ProTaper Ultimate")

        wo = ct.lookup_file_system("вейван")
        self.assertIsNotNone(wo)
        self.assertEqual(wo["system_name"], "WaveOne Gold")

        soco = ct.lookup_file_system("соко")
        self.assertIsNotNone(soco)
        self.assertEqual(soco["system_name"], "SOCO SC / SC Pro")

        rotate = ct.lookup_file_system("rotate")
        self.assertIsNotNone(rotate)
        self.assertEqual(rotate["system_name"], "VDW Rotate")

        xp = ct.lookup_file_system("xp-endo")
        self.assertIsNotNone(xp)
        self.assertEqual(xp["system_name"], "XP-endo Shaper / Finisher")

    def test_format_file_system_card(self):
        pt = ct.lookup_file_system("protaper")
        card = ct.format_file_system_card(pt)
        self.assertIn("ProTaper Ultimate", card)
        self.assertIn("Базовые обороты (RPM):", card)
        self.assertIn("Рекомендуемый торк:", card)
        self.assertIn("Спецификация инструментов:", card)
        self.assertIn("Chairside Совет:", card)

    # ─────────────────────────────────────────────────────────────
    # 3. ЭКСТРЕННАЯ АНЕСТЕЗИЯ У КРЕСЛА
    # ─────────────────────────────────────────────────────────────
    def test_anesthesia_rescue_protocols(self):
        buff = ct.CHAIRSIDE_ANESTHESIA_RESCUE.get("buffering")
        self.assertIsNotNone(buff)
        self.assertIn("8.4% NaHCO3", buff["title"])
        self.assertIn("0.18 мл", buff["recipe"])
        self.assertIn("7.35–7.45", buff["recipe"])

        gg = ct.CHAIRSIDE_ANESTHESIA_RESCUE.get("gow_gates")
        self.assertIsNotNone(gg)
        self.assertIn("Gow-Gates", gg["title"])
        self.assertIn("25 мм", gg["protocol"])

        va = ct.CHAIRSIDE_ANESTHESIA_RESCUE.get("vazirani_akinosi")
        self.assertIsNotNone(va)
        self.assertIn("Vazirani-Akinosi", va["title"])

        io = ct.CHAIRSIDE_ANESTHESIA_RESCUE.get("intraosseous")
        self.assertIsNotNone(io)
        self.assertIn("Интраоссальная", io["title"])

    # ─────────────────────────────────────────────────────────────
    # 4. СКОРАЯ ПОМОЩЬ ПО ОБЛОМКАМ ИНСТРУМЕНТОВ
    # ─────────────────────────────────────────────────────────────
    def test_fragment_protocols(self):
        coronal = ct.get_fragment_protocol("coronal_orifice")
        self.assertIsNotNone(coronal)
        self.assertTrue(coronal.ultrasound_allowed)
        self.assertEqual(coronal.action, "ИЗВЛЕЧЕНИЕ (Removal)")

        curved = ct.get_fragment_protocol("middle_curved")
        self.assertIsNotNone(curved)
        self.assertFalse(curved.ultrasound_allowed)
        self.assertIn("BYPASS", curved.action)
        self.assertIn("КРИТИЧЕСКИ ВЫСОКИЙ", curved.risk_of_perforation)

        card = ct.format_fragment_card(curved)
        self.assertIn("Протокол спасения: Обломок инструмента", card)
        self.assertIn("КАТЕГОРИЧЕСКИ ЗАПРЕЩЕН", card)
        self.assertIn("Юридически безопасный разговор с пациентом:", card)

    # ─────────────────────────────────────────────────────────────
    # 5. ФАРМАКОТЕРАПИЯ В 1 ТАП
    # ─────────────────────────────────────────────────────────────
    def test_calculate_antibiotic(self):
        # Ребенок 20 кг без аллергии
        k_res = ct.calculate_antibiotic(20.0, is_child=True)
        self.assertIn("Амоксициллин+Клавуланат", k_res.drug_name)
        self.assertIn("10.0 мл", k_res.dosage)
        self.assertIn("в холодильнике", k_res.patient_message_text)

        # Взрослый 70 кг стандарт
        a_res = ct.calculate_antibiotic(70.0, is_child=False)
        self.assertIn("Амоксиклав 875/125", a_res.drug_name)
        self.assertIn("5 дней", a_res.duration_days)

        # Взрослый аллергик на пенициллин
        al_res = ct.calculate_antibiotic(70.0, is_child=False, allergy_penicillin=True)
        self.assertIn("Кларитромицин", al_res.drug_name)
        self.assertIn("аллергии на пенициллин", al_res.patient_message_text)

        # Тяжелая инфекция (Периостит / Флегмона)
        sev_res = ct.calculate_antibiotic(75.0, is_child=False, severe_infection=True)
        self.assertIn("Метронидазол", sev_res.drug_name)
        self.assertIn("АЛКОГОЛЬ", sev_res.patient_message_text)

    def test_calculate_analgesia_and_dexa(self):
        std_analg = ct.calculate_analgesia(has_gastritis=False)
        self.assertIn("Ибупрофен + Парацетамол", std_analg)
        self.assertIn("400 мг", std_analg)

        gas_analg = ct.calculate_analgesia(has_gastritis=True)
        self.assertIn("гастрите", gas_analg)
        self.assertIn("Омепразол", gas_analg)

        dexa = ct.dexamethasone_emergency_card()
        self.assertIn("Дексаметазон", dexa)
        self.assertIn("4 мг – 8 мг", dexa)

    # ─────────────────────────────────────────────────────────────
    # 6. ЭКСПРЕСС-КОНСИЛИУМ «СПАСАТЬ ИЛИ УДАЛЯТЬ?»
    # ─────────────────────────────────────────────────────────────
    def test_preservation_concilium(self):
        good = ct.evaluate_tooth_preservation(ferrule_mm=2.5, root_fracture_suspected=False, bone_support_percent=85)
        self.assertGreaterEqual(good.total_score, 75)
        self.assertIn("СПАСАТЬ", good.verdict)
        self.assertEqual(good.color, "🟢")

        fracture = ct.evaluate_tooth_preservation(ferrule_mm=2.0, root_fracture_suspected=True)
        self.assertEqual(fracture.total_score, 0)
        self.assertIn("УДАЛЕНИЕ", fracture.verdict)
        self.assertEqual(fracture.color, "🔴")

        hopeless = ct.evaluate_tooth_preservation(ferrule_mm=0.2, bone_support_percent=20)
        self.assertLess(hopeless.total_score, 50)
        self.assertIn("НЕБЛАГОПРИЯТНЫЙ", hopeless.verdict)

    # ─────────────────────────────────────────────────────────────
    # 7. AAE CASE DIFFICULTY CALCULATOR
    # ─────────────────────────────────────────────────────────────
    def test_aae_difficulty_calculator(self):
        # Low risk: 1, 1, 1
        res_low = ct.AAEDifficultyCalculator.evaluate_case((1, 1, 1), tooth_num="Зуб 1.1")
        self.assertEqual(res_low.tier, "LOW")
        self.assertIn("СТАНДАРТНАЯ СЛОЖНОСТЬ", res_low.title)
        self.assertEqual(res_low.badge_emoji, "✅")

        # Moderate risk: 2, 2, 1
        res_mod = ct.AAEDifficultyCalculator.evaluate_case((2, 2, 1), tooth_num="Зуб 2.4")
        self.assertEqual(res_mod.tier, "MODERATE")
        self.assertIn("УМЕРЕННАЯ СЛОЖНОСТЬ", res_mod.title)
        self.assertEqual(res_mod.badge_emoji, "⚠️")

        # High risk: 1, 1, 3
        res_high1 = ct.AAEDifficultyCalculator.evaluate_case((1, 1, 3), tooth_num="Зуб 3.6")
        self.assertEqual(res_high1.tier, "HIGH")
        self.assertIn("ВЫСОКАЯ СЛОЖНОСТЬ", res_high1.title)
        self.assertEqual(res_high1.badge_emoji, "🚨")

        # High risk: 2, 2, 3
        res_high2 = ct.AAEDifficultyCalculator.evaluate_case((2, 2, 3), tooth_num="Зуб 4.7")
        self.assertEqual(res_high2.tier, "HIGH")
        self.assertIn("ВЫСОКАЯ СЛОЖНОСТЬ", res_high2.title)

        # Проверка карточки
        self.assertIn("КЛИНИЧЕСКИЙ РАСЧЕТ СЛОЖНОСТИ ЭНДО (AAE)", res_high2.shareable_card_text)
        self.assertIn("Зуб 4.7", res_high2.shareable_card_text)
        self.assertIn("Обязательное оснащение:", res_high2.shareable_card_text)
        self.assertIn("микроскоп", res_high2.shareable_card_text.lower())

    # ─────────────────────────────────────────────────────────────
    # 8. MARKUPS & DISPATCHER
    # ─────────────────────────────────────────────────────────────
    def test_markups_generation(self):
        self.assertTrue(len(ct.build_chairside_hub_markup()) >= 4)
        self.assertTrue(len(ct.build_fdi_quadrant_selector_markup()) >= 3)
        self.assertTrue(len(ct.build_fdi_quadrant_teeth_markup(1)) >= 2)
        self.assertTrue(len(ct.build_fdi_tooth_actions_markup(16)) >= 3)
        self.assertTrue(len(ct.build_files_catalog_markup()) >= 4)
        self.assertTrue(len(ct.build_broken_file_matrix_markup()) >= 4)
        self.assertTrue(len(ct.build_anesthesia_sos_markup()) >= 3)
        self.assertTrue(len(ct.build_pharma_quick_markup()) >= 3)
        self.assertTrue(len(ct.build_aae_step_markup(1)) >= 3)

    def test_callback_dispatcher_execution(self):
        async def run_dispatch():
            event = AsyncMock()
            event.edit = AsyncMock()
            event.answer = AsyncMock()
            bot_client = MagicMock()

            # Chairside hub
            ok = await ct.dispatch_chairside_callback(bot_client, event, "chairside:hub")
            self.assertTrue(ok)
            event.edit.assert_called()

            # FDI menu
            ok = await ct.dispatch_chairside_callback(bot_client, event, "fdi:menu")
            self.assertTrue(ok)

            # FDI tooth
            ok = await ct.dispatch_chairside_callback(bot_client, event, "fdi:tooth:16")
            self.assertTrue(ok)

            # Files menu
            ok = await ct.dispatch_chairside_callback(bot_client, event, "files:menu")
            self.assertTrue(ok)

            # File sys detail
            ok = await ct.dispatch_chairside_callback(bot_client, event, "file_sys:protaper_ultimate")
            self.assertTrue(ok)

            # AAE start
            ok = await ct.dispatch_chairside_callback(bot_client, event, "aae:start:46")
            self.assertTrue(ok)

            # AAE step 1
            ok = await ct.dispatch_chairside_callback(bot_client, event, "aae:s1:2:46")
            self.assertTrue(ok)

            # AAE step 2
            ok = await ct.dispatch_chairside_callback(bot_client, event, "aae:s2:2:2:46")
            self.assertTrue(ok)

            # AAE step 3 final eval
            ok = await ct.dispatch_chairside_callback(bot_client, event, "aae:s3:2:2:3:46")
            self.assertTrue(ok)

            # Anesthesia buffering
            ok = await ct.dispatch_chairside_callback(bot_client, event, "anes_sos:buffering")
            self.assertTrue(ok)

            # Broken file bypass
            ok = await ct.dispatch_chairside_callback(bot_client, event, "file_frag:middle_curved")
            self.assertTrue(ok)

            # Pharma adult
            ok = await ct.dispatch_chairside_callback(bot_client, event, "pharma:adult:70")
            self.assertTrue(ok)

            # Preservation eval
            ok = await ct.dispatch_chairside_callback(bot_client, event, "pres_eval:2.0:0:80:0")
            self.assertTrue(ok)

            # Unknown callback
            ok_unknown = await ct.dispatch_chairside_callback(bot_client, event, "unknown:callback:123")
            self.assertFalse(ok_unknown)

        asyncio.run(run_dispatch())


if __name__ == "__main__":
    unittest.main()
