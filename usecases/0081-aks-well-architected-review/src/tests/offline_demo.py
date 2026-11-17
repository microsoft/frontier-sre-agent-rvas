"""Create the four generic SIMULATED files without authentication or Azure calls."""

import json

from support import REFERENCE, fixture, load_engine


def main():
    engine = load_engine(standalone=True)
    raw = fixture(engine)
    raw["inventory"]["node_pools"][0]["provisioning_state"] = "Failed"
    snapshot = engine.finish_snapshot(raw, REFERENCE, "SIMULATED", "LAB")
    result = engine.write_report(snapshot)
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
