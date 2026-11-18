"""Write a permanently SIMULATED report from mocked source pages; never Azure."""

import argparse
import json
import os
from pathlib import Path

from support import FakeReader, snapshot, tool


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="Existing local scratch directory, not live runtime configuration.")
    args = parser.parse_args()
    root = args.output.resolve(strict=True)
    if not root.is_dir():
        parser.error("--output must name an existing local scratch directory.")
    document = snapshot(FakeReader(extra_events=28))
    previous = Path.cwd()
    try:
        os.chdir(root)
        response = tool.write_report(document, tool.logo_markup())
    finally:
        os.chdir(previous)
    print(json.dumps(response))


if __name__ == "__main__":
    main()
