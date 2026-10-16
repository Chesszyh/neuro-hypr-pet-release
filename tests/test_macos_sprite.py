import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from src.controller import load_image_set, make_runtime
from src.desktop import MonitorInfo

if sys.platform == 'darwin':
    from src.macos.sprite_window import load_sprite


@unittest.skipUnless(sys.platform == 'darwin', 'Requires AppKit')
class SpritePixelsTest(unittest.TestCase):
    def test_png_dpi_does_not_change_sprite_dimensions(self):
        with tempfile.TemporaryDirectory() as folder:
            sizes = []
            for dpi in (72, 144, 300):
                path = Path(folder) / f'frame-{dpi}.png'
                Image.new('RGBA', (128, 128), (255, 100, 100, 255)).save(path, dpi=(dpi, dpi))
                image = load_sprite(path)
                sizes.append((image.size().width, image.size().height))
            self.assertEqual(sizes, [(128, 128)] * 3)

    def test_real_neuron_walking_frames_keep_floor_anchors_in_both_directions(self):
        collection = Path(__file__).resolve().parents[1] / 'refs/The-Neuroling-Collection'
        if not (collection / 'img/Neuron/conf/actions.xml').is_file():
            self.skipTest('Requires extended Neuron assets')
        catalog, behaviors = load_image_set(collection, 'Neuron')
        monitor = MonitorInfo('test', 0, 0, 1470, 956, 2, (0, 33, 0, 74))
        runtime = make_runtime(catalog, monitor, behaviors)
        runtime.start_action('Walk')
        runtime.anchor_x, runtime.anchor_y = 735, 882
        for frame_index in range(len(runtime.action.frames)):
            runtime.frame_index = frame_index
            frame = runtime.frame
            image = load_sprite(catalog.image_set_dir / frame.image)
            width, height = round(image.size().width), round(image.size().height)
            for direction in (False, True):
                runtime.look_right = direction
                rect = runtime.sprite_rect(width, height)
                self.assertEqual(rect.bottom, 882)
                self.assertLessEqual(rect.left, runtime.anchor_x)
                self.assertGreater(rect.right, runtime.anchor_x)
