"""Regression checks for unsafe departure claims and fixed-appointment movement."""
import copy
import unittest

from apps.kep_preview.planner import plan


def example():
    return {
        "date": "2026-10-20",
        "stops": [
            {"id": "maslak", "label": "Maslak", "arrival": "16:00", "duration_minutes": 30},
            {"id": "levent", "label": "Levent", "arrival": "17:00", "duration_minutes": 45},
            {"id": "dinner", "label": "Ekip yemeği", "arrival": None, "duration_minutes": 60},
            {"id": "zorlu", "label": "Zorlu PSM", "arrival": "20:00", "duration_minutes": None},
        ],
        "travel_minutes": [10, 15, 20],
        "arrival_buffer_minutes": 15,
    }


class PlannerTests(unittest.TestCase):
    def test_flexible_dinner_and_backwards_departure_preserve_fixed_appointments(self):
        result = plan(example())
        self.assertEqual(result["status"], "feasible")
        self.assertEqual([s["planned_arrival"] for s in result["stops"]],
                         ["16:00", "17:00", "18:00", "20:00"])
        self.assertEqual(result["stops"][2]["planned_departure"], "19:00")
        self.assertEqual([leg["latest_departure"] for leg in result["legs"]],
                         ["16:35", "18:10", "19:25"])
        self.assertEqual([leg["slack_minutes"] for leg in result["legs"]], [5, 25, 25])
        self.assertFalse(result["traffic_live"])
        self.assertEqual(result["basis"], "manual_estimates")

    def test_buffer_can_make_an_otherwise_possible_connection_fail(self):
        request = example()
        request["stops"][0]["duration_minutes"] = 45
        request["travel_minutes"][0] = 15
        request["arrival_buffer_minutes"] = 0
        self.assertEqual(plan(request)["status"], "feasible")
        request["arrival_buffer_minutes"] = 15
        result = plan(request)
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(result["stops"][1]["planned_arrival"], "17:00")
        self.assertEqual(result["legs"][0]["latest_departure"], "16:30")
        self.assertEqual(result["legs"][0]["slack_minutes"], -15)

    def test_dinner_conflict_never_moves_zorlu_or_reports_feasibility(self):
        request = example()
        request["stops"][2]["duration_minutes"] = 100
        result = plan(request)
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(result["stops"][-1]["planned_arrival"], "20:00")
        self.assertEqual(result["legs"][-1]["slack_minutes"], -15)

    def test_incomplete_estimates_never_supply_departure_claims(self):
        request = example()
        request["travel_minutes"][1] = None
        result = plan(request)
        self.assertEqual(result["status"], "needs_input")
        self.assertTrue(result["missing"])
        self.assertTrue(all(s["planned_departure"] is None for s in result["stops"]))
        self.assertTrue(all(leg["latest_departure"] is None and leg["slack_minutes"] is None
                            for leg in result["legs"]))
        self.assertEqual(result["stops"][-1]["planned_arrival"], "20:00")

    def test_missing_beginning_is_not_invented_from_next_appointment(self):
        request = example()
        request["stops"][0]["arrival"] = None
        result = plan(request)
        self.assertEqual(result["status"], "needs_input")
        self.assertIsNone(result["stops"][0]["planned_arrival"])

    def test_missing_travel_cannot_hide_a_certain_appointment_conflict(self):
        request = example()
        request["stops"] = [
            {"id": "a", "label": "A", "arrival": "16:00", "duration_minutes": 90},
            {"id": "b", "label": "B", "arrival": "17:00", "duration_minutes": None},
        ]
        request["travel_minutes"] = [None]
        request["arrival_buffer_minutes"] = 0
        result = plan(request)
        self.assertEqual(result["status"], "conflict")
        self.assertTrue(result["missing"])
        self.assertTrue(any("en az 30 dakika eksik" in item for item in result["conflicts"]))
        self.assertEqual([stop["planned_arrival"] for stop in result["stops"]],
                         ["16:00", "17:00"])
        self.assertTrue(all(stop["planned_departure"] is None for stop in result["stops"]))
        self.assertTrue(all(leg["latest_departure"] is None and leg["slack_minutes"] is None
                            for leg in result["legs"]))

    def test_missing_duration_cannot_hide_a_certain_day_overflow(self):
        request = example()
        request["stops"] = [
            {"id": "a", "label": "A", "arrival": "23:00", "duration_minutes": None},
            {"id": "b", "label": "B", "arrival": None, "duration_minutes": 0},
        ]
        request["travel_minutes"] = [90]
        request["arrival_buffer_minutes"] = 0
        result = plan(request)
        self.assertEqual(result["status"], "conflict")
        self.assertTrue(result["missing"])
        self.assertTrue(any("seçilen günü aşıyor" in item for item in result["conflicts"]))
        self.assertIsNone(result["stops"][1]["planned_arrival"])
        self.assertTrue(all(stop["planned_departure"] is None for stop in result["stops"]))
        self.assertTrue(all(leg["latest_departure"] is None and leg["slack_minutes"] is None
                            for leg in result["legs"]))

    def test_last_duration_is_not_required_for_arrival_planning(self):
        result = plan(example())
        self.assertFalse(result["missing"])
        self.assertIsNone(result["stops"][-1]["planned_departure"])

    def test_multiple_flexible_stops_keep_their_order(self):
        request = example()
        request["stops"].insert(3, {
            "id": "coffee", "label": "Kahve", "arrival": None, "duration_minutes": 10,
        })
        request["travel_minutes"] = [10, 15, 5, 20]
        result = plan(request)
        self.assertEqual(result["status"], "feasible")
        self.assertEqual([s["id"] for s in result["stops"]],
                         ["maslak", "levent", "dinner", "coffee", "zorlu"])
        self.assertEqual(result["stops"][3]["planned_arrival"], "19:05")
        self.assertEqual(result["legs"][1]["slack_minutes"], 10)

    def test_cross_midnight_is_a_conflict_not_a_clock_wrap(self):
        request = example()
        request["stops"] = [
            {"id": "a", "label": "Geç toplantı", "arrival": "23:30", "duration_minutes": 45},
            {"id": "b", "label": "Yemek", "arrival": None, "duration_minutes": 30},
        ]
        request["travel_minutes"] = [20]
        result = plan(request)
        self.assertEqual(result["status"], "conflict")
        self.assertIsNone(result["stops"][0]["planned_departure"])
        self.assertIsNone(result["stops"][1]["planned_arrival"])

    def test_known_bad_fixed_order_is_reported_even_when_durations_are_unknown(self):
        request = example()
        request["stops"][1]["arrival"] = "15:00"
        request["stops"][0]["duration_minutes"] = None
        result = plan(request)
        self.assertEqual(result["status"], "conflict")
        self.assertTrue(result["missing"])
        self.assertEqual(result["stops"][1]["planned_arrival"], "15:00")

    def test_no_later_anchor_means_no_invented_latest_departure(self):
        request = example()
        request["stops"][-1]["arrival"] = None
        result = plan(request)
        self.assertEqual(result["status"], "feasible")
        self.assertEqual(result["stops"][-1]["planned_arrival"], "19:20")
        self.assertIsNone(result["legs"][-1]["latest_departure"])

    def test_rejects_unsafe_scalar_and_schema_inputs(self):
        mutations = [
            lambda p: p.update(traffic_live=True),
            lambda p: p.update(date="2026-02-30"),
            lambda p: p.update(date="20261020"),
            lambda p: p.update(arrival_buffer_minutes=True),
            lambda p: p.update(arrival_buffer_minutes=None),
            lambda p: p["stops"][0].update(arrival="24:00"),
            lambda p: p["stops"][0].update(arrival="9:00"),
            lambda p: p["stops"][0].update(arrival=True),
            lambda p: p["stops"][0].update(duration_minutes=True),
            lambda p: p["stops"][0].update(duration_minutes=45.0),
            lambda p: p["stops"][0].update(duration_minutes=-1),
            lambda p: p["stops"][0].update(duration_minutes=1441),
            lambda p: p["stops"][0].update(duration_minutes=float("nan")),
            lambda p: p["stops"][0].update(verified=True),
            lambda p: p["stops"][0].update(label="\n"),
            lambda p: p["stops"][1].update(id="maslak"),
            lambda p: p.update(travel_minutes=[10, 20]),
            lambda p: p.update(travel_minutes=[10, True, 20]),
            lambda p: p.update(travel_minutes=[10, float("inf"), 20]),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(case=index):
                request = example()
                mutate(request)
                with self.assertRaises(ValueError):
                    plan(request)

    def test_request_is_not_mutated(self):
        request = example()
        original = copy.deepcopy(request)
        plan(request)
        self.assertEqual(request, original)


if __name__ == "__main__":
    unittest.main()
