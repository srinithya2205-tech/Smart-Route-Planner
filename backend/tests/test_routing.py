"""Unit tests for Smart Route's backend routing helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import Location, RouteRequest, _normalise_osrm_route, _rank_route


def feature(duration: float, unnamed_ratio: float) -> dict:
    return {
        "properties": {
            "summary": {"distance": 1000.0, "duration": duration},
            "road_quality": {"unnamed_distance_ratio": unnamed_ratio},
        }
    }


class RouteRankingTests(unittest.TestCase):
    def test_fastest_preference_uses_duration(self) -> None:
        quick_but_unnamed = feature(100, 0.90)
        slower_named = feature(115, 0.00)

        self.assertLess(
            _rank_route(quick_but_unnamed, "fastest", 100),
            _rank_route(slower_named, "fastest", 100),
        )

    def test_named_roads_preference_can_choose_slower_named_route(self) -> None:
        quick_but_unnamed = feature(100, 0.90)
        slower_named = feature(115, 0.00)

        self.assertLess(
            _rank_route(slower_named, "named_roads", 100),
            _rank_route(quick_but_unnamed, "named_roads", 100),
        )

    def test_balanced_preference_combines_time_and_unnamed_distance(self) -> None:
        quick_but_unnamed = feature(100, 0.90)
        slower_named = feature(115, 0.00)

        self.assertLess(
            _rank_route(slower_named, "balanced", 100),
            _rank_route(quick_but_unnamed, "balanced", 100),
        )

    def test_route_normalisation_reports_named_and_unnamed_distance(self) -> None:
        route = {
            "distance": 1000,
            "duration": 300,
            "geometry": {
                "type": "LineString",
                "coordinates": [[77.0, 12.0], [77.1, 12.1]],
            },
            "legs": [
                {
                    "distance": 1000,
                    "duration": 300,
                    "steps": [
                        {
                            "distance": 600,
                            "duration": 180,
                            "name": "NH 48",
                            "ref": "NH 48",
                            "maneuver": {"type": "depart"},
                        },
                        {
                            "distance": 400,
                            "duration": 120,
                            "name": "",
                            "ref": "",
                            "maneuver": {"type": "continue", "modifier": "straight"},
                        },
                    ],
                }
            ],
        }

        normalised = _normalise_osrm_route(route)
        quality = normalised["properties"]["road_quality"]

        self.assertEqual(normalised["properties"]["summary"]["distance"], 1000)
        self.assertEqual(quality["named_distance"], 600)
        self.assertEqual(quality["unnamed_distance"], 400)
        self.assertEqual(quality["unnamed_distance_ratio"], 0.4)
        self.assertEqual(quality["unnamed_step_count"], 1)


class RequestValidationTests(unittest.TestCase):
    def test_accepts_india_coordinates_and_walking_profile(self) -> None:
        request = RouteRequest(
            start=Location(lat=12.9716, lon=77.5946),
            destination=Location(lat=13.0827, lon=80.2707),
            profile="foot-walking",
            road_preference="balanced",
        )
        self.assertEqual(request.profile, "foot-walking")
        self.assertEqual(request.road_preference, "balanced")

    def test_rejects_out_of_range_coordinates(self) -> None:
        with self.assertRaises(Exception):
            Location(lat=120, lon=77.0)

    def test_rejects_unknown_travel_profiles(self) -> None:
        with self.assertRaises(Exception):
            RouteRequest(
                start=Location(lat=12.9716, lon=77.5946),
                destination=Location(lat=13.0827, lon=80.2707),
                profile="train",
            )


if __name__ == "__main__":
    unittest.main()
