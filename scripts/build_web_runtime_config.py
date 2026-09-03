from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "web" / "runtime-config.js"


def render_runtime_config(carto_key: str) -> str:
    return (
        "window.MuseRuntimeConfig = Object.freeze({\n"
        f"  cartoBasemapKey: {json.dumps(carto_key)},\n"
        "});\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build browser runtime configuration for Pages.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--require-carto-key", action="store_true")
    args = parser.parse_args()

    carto_key = os.environ.get("CARTO_BASEMAP_KEY", "").strip()
    if args.require_carto_key and not carto_key:
        raise SystemExit("CARTO_BASEMAP_KEY is required for Pages deployment")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_runtime_config(carto_key), encoding="utf-8")


if __name__ == "__main__":
    main()
