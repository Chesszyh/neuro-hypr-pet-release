#!/usr/bin/env python3
"""Run a timed desktop trial using isolated preferences and user-supplied assets."""
import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.macos import app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collection', type=Path, required=True)
    parser.add_argument('--image-set', default='Neuron')
    parser.add_argument('--count', type=int, choices=(1, 5, 20), default=1)
    parser.add_argument('--duration', type=float, default=10)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    launch = app.MacApplication.launch
    def start(application):
        launch(application)
        for _ in range(args.count - 1):
            application.manager.spawn(args.image_set)
    app.MacApplication.launch = start
    with tempfile.TemporaryDirectory(prefix='neuro-macos-smoke-') as folder:
        preferences = Path(folder) / 'preferences.json'
        preferences.write_text(json.dumps({'image_sets': [args.image_set]}))
        app.main(['--collection', str(args.collection), '--preferences', str(preferences),
                  '--duration', str(args.duration), '--report', str(args.report)])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
