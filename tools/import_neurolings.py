#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from zipfile import BadZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.assets import DOWNLOAD_PAGE, default_collection, import_collection


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=f"Import Neurolings v1.zip downloaded from {DOWNLOAD_PAGE}")
    parser.add_argument("archive", type=Path)
    parser.add_argument("--destination", type=Path, default=default_collection(), help="New collection directory; defaults to the XDG user data directory.")
    args = parser.parse_args(argv)
    try:
        names = import_collection(args.archive, args.destination)
    except (OSError, ValueError, BadZipFile) as error:
        print(f"Import failed: {error}", file=sys.stderr)
        return 1
    print(f"Imported {', '.join(names)} into {args.destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
