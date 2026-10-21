"""Integration boundaries that can otherwise weaken a user's constraints."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from apps.kep_preview import service


class DiscoveryBoundaryTests(unittest.TestCase):
    def test_bootstrap_uses_current_time_and_keeps_research_scope(self):
        at = "2030-02-03T04:05:06+03:00"
        with patch.object(service, "_now_iso", return_value=at):
            data = service.bootstrap()
        self.assertEqual(data["initial"]["query"]["at"], at)
        self.assertEqual(data["meta"]["catalog_count"], 7)
        self.assertFalse(data["meta"]["consumer_publish"])
        self.assertEqual({c["id"]: c["count"] for c in data["categories"]}, {
            "discover": 7, "food": 0, "events": 0, "services": 0,
        })
        self.assertTrue(all(not r["live_verified"] for r in data["initial"]["decision"]["selected"]))

    def test_coordinates_only_augment_core_selected_ids(self):
        response = service.discover({"radius_km": 1})
        rows = response["decision"]["selected"]
        self.assertEqual(len(rows), 3)
        self.assertNotIn("blocked", response["decision"])
        self.assertTrue(all(r["distance_type"] == "straight_line" for r in rows))
        self.assertTrue(all(r["lat"] and r["lon"] and r["source_url"] for r in rows))
        self.assertTrue(all(r["price"] is None for r in rows))

    def test_missing_live_evidence_cannot_turn_into_recommendation(self):
        response = service.discover({"open_now": True, "budget": 500})
        self.assertEqual(response["decision"]["action"], "REFRESH")
        self.assertEqual(response["decision"]["selected"], [])
        self.assertIn("PRICE_UNKNOWN", response["decision"]["reasons"])
        self.assertIn("OPENING_HOURS_UNKNOWN", response["decision"]["reasons"])

    def test_cannot_inject_core_policy_location_or_proactive_fields(self):
        invalid = [
            {"lat": 0}, {"city": "İzmir"}, {"policy": "simple_safe"}, {"push_opt_in": True},
            {"category": []}, {"mode": []}, {"budget": True}, {"radius_km": False},
            {"budget": float("nan")}, {"budget": float("inf")}, {"budget": 10 ** 1000}, {"open_now": "false"},
            {"quiet": 0}, {"radius_km": -1}, {"radius_km": 21},
            {"at": "2026-10-20"}, {"at": "2026-02-30T12:00:00"},
            {"at": True}, [], None,
        ]
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                service.discover(payload)

    def test_source_rights_remain_a_core_gate(self):
        catalog = deepcopy(service.load_catalog())
        for row in catalog:
            row["rights_scope"] = "not_approved"
        with patch.object(service, "load_catalog", return_value=catalog):
            response = service.discover({"radius_km": 20})
        self.assertEqual(response["decision"]["selected"], [])
        self.assertEqual(response["decision"]["action"], "ABSTAIN")

    def test_empty_categories_never_borrow_other_categories_or_cities(self):
        for category in ("food", "events", "services"):
            with self.subTest(category=category):
                response = service.discover({"category": category, "radius_km": 20})
                self.assertEqual(response["decision"]["selected"], [])

    def test_place_subtype_must_match_its_public_category(self):
        for category, subtype in (("discover", "museum"), ("food", "restaurant"), ("food", "cafe")):
            with self.subTest(category=category, subtype=subtype):
                response = service.discover({"category": category, "place_category": subtype})
                self.assertEqual(response["query"]["place_category"], subtype)
        invalid = [
            {"category": "food", "place_category": "museum"},
            {"category": "discover", "place_category": "cafe"},
            {"category": "events", "place_category": "restaurant"},
            {"category": "services", "place_category": "museum"},
            {"place_category": "park"}, {"place_category": []}, {"place_category": True},
        ]
        with patch.object(service, "decide", wraps=service.decide) as decide:
            for payload in invalid:
                with self.subTest(payload=payload), self.assertRaises(ValueError):
                    service.discover(payload)
            decide.assert_not_called()


class BoundedTextTests(unittest.TestCase):
    def test_turkish_message_maps_to_actual_core_gates(self):
        response = service.chat({"message": "Hey Kep, Galata çevresinde 1 km içinde şimdi açık ve 500 TL altında yer bul."})
        self.assertEqual(response["query"]["budget"], 500)
        self.assertEqual(response["query"]["radius_km"], 1)
        self.assertTrue(response["query"]["open_now"])
        self.assertEqual(response["decision"]["action"], "REFRESH")
        self.assertFalse(response["meta"]["model_used"])

    def test_museum_constraint_is_not_widened_to_every_discovery_place(self):
        response = service.chat({"message": "20 km içinde müze bul"})
        self.assertTrue(response["decision"]["selected"])
        self.assertTrue(all(r["category"] == "museum" for r in response["decision"]["selected"]))
        self.assertEqual(response["interpretation"]["place_category"], "museum")
        self.assertEqual(response["query"]["place_category"], "museum")
        cafe = service.chat({"message": "Kafe bul"})
        self.assertEqual(cafe["interpretation"]["place_category"], "cafe")
        self.assertEqual(cafe["query"]["place_category"], "cafe")
        self.assertEqual(cafe["decision"]["selected"], [])

    def test_subtype_survives_chat_and_structured_radius_follow_ups(self):
        first = service.chat({"message": "1 km içinde müze bul"})
        repeated = service.chat({"message": "20 km içinde göster", "filters": first["query"]})
        expanded = service.discover(dict(first["query"], radius_km=20))
        for response in (repeated, expanded):
            with self.subTest(query=response["query"]):
                self.assertEqual(response["query"]["place_category"], "museum")
                self.assertEqual(response["query"]["radius_km"], 20)
                self.assertGreater(len(response["decision"]["selected"]), len(first["decision"]["selected"]))
                self.assertTrue(all(row["category"] == "museum" for row in response["decision"]["selected"]))
        self.assertEqual(repeated["interpretation"]["place_category"], "museum")
        self.assertEqual(first["query"]["radius_km"], 1)

    def test_explicit_general_category_resets_inherited_subtype(self):
        first = service.chat({"message": "20 km içinde müze bul"})
        for message, category in (("Keşif göster", "discover"), ("Yemek bul", "food"),
                                  ("Etkinlik bul", "events"), ("Hizmet bul", "services")):
            with self.subTest(message=message):
                response = service.chat({"message": message, "filters": first["query"]})
                self.assertEqual(response["query"]["category"], category)
                self.assertIsNone(response["query"]["place_category"])
                self.assertIsNone(response["interpretation"]["place_category"])
                if category == "discover":
                    self.assertEqual({row["category"] for row in response["decision"]["selected"]},
                                     {"museum", "heritage", "park"})
        cleared = service.discover(dict(first["query"], place_category=None))
        self.assertIsNone(cleared["query"]["place_category"])
        self.assertGreater(len(cleared["decision"]["selected"]), len(first["decision"]["selected"]))

    def test_unsupported_constraints_stop_query_without_mutating_filters(self):
        messages = [
            "Galata'da vegan yemek bul", "Beşiktaş çevresinde yer bul", "Yarın açık müze bul",
            "Müze hariç yer bul", "Açık olmasın", "Sakin değil kalabalık yer bul",
            "En iyi müzeleri göster", "500 TL altında steakhouse bul",
            "Galata çevresinde ucuz yer bul", "1.000 TL altında yer bul",
            "2 km içinde 500 TL altında ücretsiz müze bul", "</script><script>alert(1)</script>",
        ]
        base = {"category": "discover", "budget": 800, "radius_km": 5}
        with patch.object(service, "decide", wraps=service.decide) as decide:
            for message in messages:
                with self.subTest(message=message):
                    response = service.chat({"message": message, "filters": base})
                    self.assertIsNone(response["decision"])
                    self.assertTrue(response["clarifications"])
                    self.assertEqual(response["query"]["budget"], 800)
                    self.assertEqual(response["query"]["radius_km"], 5)
            decide.assert_not_called()
        self.assertEqual(base, {"category": "discover", "budget": 800, "radius_km": 5})

    def test_preserves_existing_filters_and_does_not_infer_user_location(self):
        response = service.chat({"message": "Müze bul", "filters": {"open_now": True, "radius_km": 3}})
        self.assertTrue(response["query"]["open_now"])
        self.assertEqual(response["query"]["radius_km"], 3)
        self.assertEqual(response["decision"]["action"], "REFRESH")
        self.assertIsNone(service.chat({"message": "Yakınımda müze bul"})["decision"])

    def test_ne_ne_negation_cannot_become_positive_filters(self):
        with patch.object(service, "decide", wraps=service.decide) as decide:
            response = service.chat({
                "message": "Ne sakin ne açık yer bul",
                "filters": {"quiet": False, "open_now": False, "radius_km": 3},
            })
            decide.assert_not_called()
        self.assertIsNone(response["decision"])
        self.assertTrue(response["clarifications"])
        self.assertFalse(response["query"]["quiet"])
        self.assertFalse(response["query"]["open_now"])
        self.assertEqual(response["query"]["radius_km"], 3)

    def test_result_count_bound_cannot_disappear_but_budget_bound_is_supported(self):
        with patch.object(service, "decide", wraps=service.decide) as decide:
            for text in ("20 km içinde en fazla bir müze öner", "20 km içinde en fazla bir yer öner"):
                with self.subTest(message=text):
                    response = service.chat({"message": text, "filters": {"radius_km": 1}})
                    self.assertIsNone(response["decision"])
                    self.assertTrue(response["clarifications"])
                    self.assertEqual(response["query"]["radius_km"], 1)
            decide.assert_not_called()
        budget = service.chat({"message": "Galata çevresinde en fazla 500 TL bütçeyle yer bul"})
        self.assertEqual(budget["query"]["budget"], 500)
        self.assertEqual(budget["decision"]["action"], "REFRESH")

    def test_ambiguity_and_planning_are_not_treated_as_discovery(self):
        for text in ("1 km veya 3 km içinde yer bul", "500 TL 700 TL altında yer bul", "Müze ve restoran bul", "Restoran ve kafe bul"):
            self.assertIsNone(service.chat({"message": text})["decision"])
        planned = service.chat({"message": "16'da Maslak 17'de Levent 20'de Zorlu planla"})
        self.assertIsNone(planned["decision"])
        self.assertEqual(planned["interpretation"]["route_to"], "plan")

    def test_explicit_now_overrides_inherited_time_and_modes_remain_separate(self):
        at = "2030-02-03T04:05:06+03:00"
        with patch.object(service, "_now_iso", return_value=at):
            response = service.chat({"message": "Sessiz modunda şimdi açık yer bul", "filters": {"at": "2026-10-10T18:00:00+03:00"}})
        self.assertEqual(response["query"]["mode"], "silent")
        self.assertFalse(response["query"]["quiet"])
        self.assertEqual(response["query"]["at"], at)
        self.assertEqual(response["decision"]["action"], "REFRESH")

    def test_malformed_request_fails_before_parser(self):
        for payload in ({}, {"message": " "}, {"message": 8}, {"message": "x" * 1001}, {"message": "yer bul", "policy": "skip"}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                service.chat(payload)


if __name__ == "__main__":
    unittest.main()
