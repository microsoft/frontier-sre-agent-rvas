# Source

Optional. Use this folder when a tool is built from several source files, for example an engine, a rule catalog and an HTML template. Add `build_tool.py` that writes the built file to `../manifests/tools/` and supports `--check`. `usecases.sh validate` runs `python3 src/build_tool.py --check` and fails if the checked-in build is stale. Keep unit tests in `src/tests/`. Delete this folder if the tool is a single file.
