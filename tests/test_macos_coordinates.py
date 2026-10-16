import unittest

from src.macos.coordinates import Coordinates
from src.runtime import Rect


class CoordinatesTest(unittest.TestCase):
    def test_primary_and_surrounding_screens_round_trip_in_logical_points(self):
        coordinates = Coordinates(956)
        cases = [
            ((0, 0, 1470, 956), Rect(0, 0, 1470, 956)),
            ((-1920, 0, 1920, 1080), Rect(-1920, -124, 1920, 1080)),
            ((0, 956, 1920, 1080), Rect(0, -1080, 1920, 1080)),
            ((0, -1080, 1920, 1080), Rect(0, 956, 1920, 1080)),
            ((1470, -100, 1080, 1920), Rect(1470, -864, 1080, 1920)),
        ]
        for appkit, expected in cases:
            with self.subTest(appkit=appkit):
                result = coordinates.rect_from_appkit(*appkit)
                self.assertEqual(result, expected)
                origin, size = coordinates.rect_to_appkit(result)
                self.assertEqual((*origin, *size), appkit)

    def test_pointer_conversion_does_not_subtract_sprite_height(self):
        self.assertEqual(Coordinates(956).point_from_appkit(-100, 1056), (-100, -100))

    def test_primary_reference_changes_independently_of_bounding_box(self):
        self.assertEqual(Coordinates(1080).rect_from_appkit(0, 1080, 1470, 956), Rect(0, -956, 1470, 956))
