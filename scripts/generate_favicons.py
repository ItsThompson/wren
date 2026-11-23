# /// script
# requires-python = ">=3.13"
# dependencies = ["Pillow==13.0.0", "coloraide==8.17"]
# ///
"""Run: uv run scripts/generate_favicons.py. Requires rsvg-convert (brew install librsvg)."""

import argparse
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from xml.etree import ElementTree

from coloraide import Color
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SVG_NAMESPACE = "http://www.w3.org/2000/svg"
PNG_SIZES = {
    "favicon-16x16.png": 16,
    "favicon-32x32.png": 32,
    "apple-touch-icon.png": 180,
    "android-chrome-192x192.png": 192,
    "android-chrome-512x512.png": 512,
}
ICO_SIZES = {(16, 16), (32, 32), (48, 48)}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate Wren favicons from the shared brand and theme."
    )
    parser.add_argument("--source", type=Path, default=ROOT / "shared/branding/icon.svg")
    parser.add_argument(
        "--output-dir",
        type=Path,
        nargs="+",
        default=[ROOT / "frontend/public", ROOT / "docs-site/docs/public"],
    )
    args = parser.parse_args()
    renderer = shutil.which("rsvg-convert")
    if renderer is None:
        raise RuntimeError("Install rsvg-convert before generating favicons: brew install librsvg")

    theme = (ROOT / "shared/theme/tokens.css").read_text()
    colors = {}
    for name in ("background", "primary"):
        match = re.search(rf"--{name}:\s*([^;]+);", theme)
        if match is None:
            raise ValueError(f"Missing shared theme token: --{name}")
        colors[name] = Color(match[1]).convert("srgb").to_string(hex=True)
    background = (*bytes.fromhex(colors["background"][1:]), 255)

    ElementTree.register_namespace("", SVG_NAMESPACE)
    svg = ElementTree.parse(args.source)  # noqa: S314  # Local, trusted artwork only.
    root = svg.getroot()
    for path in root.iter(f"{{{SVG_NAMESPACE}}}path"):
        path.set("fill", colors["primary"])
    title = root.find(f"{{{SVG_NAMESPACE}}}title")
    if title is not None:
        title.text = "Wren"
    root.insert(
        0,
        ElementTree.Element(
            f"{{{SVG_NAMESPACE}}}rect",
            {"width": "96", "height": "96", "fill": colors["background"]},
        ),
    )

    with tempfile.TemporaryDirectory(prefix="wren-favicons-") as workspace:
        staging = Path(workspace)
        svg.write(staging / "favicon.svg", encoding="unicode")
        for filename, size in PNG_SIZES.items():
            subprocess.run(  # noqa: S603  # Resolved renderer, fixed flags, no shell.
                [
                    renderer, "--width", str(size), "--height", str(size),
                    str(staging / "favicon.svg"), "--output", str(staging / filename),
                ],
                check=True,
            )
        with Image.open(staging / "android-chrome-512x512.png") as image:
            image.save(staging / "favicon.ico", format="ICO", sizes=sorted(ICO_SIZES))

        # Validate the whole package before replacing any existing assets.
        for filename, size in PNG_SIZES.items():
            with Image.open(staging / filename) as image:
                rgba = image.convert("RGBA")
                if image.size != (size, size) or rgba.getchannel("A").getextrema() != (255, 255):
                    raise ValueError(f"Incorrect dimensions or transparent pixels: {filename}")
                corners = ((0, 0), (size - 1, 0), (0, size - 1), (size - 1, size - 1))
                if any(rgba.getpixel(corner) != background for corner in corners):
                    raise ValueError(f"Incorrect background color: {filename}")
        with Image.open(staging / "favicon.ico") as icon:
            if icon.ico.sizes() != ICO_SIZES:
                raise ValueError("The ICO must contain 16, 32, and 48 pixel frames")
            for size in ICO_SIZES:
                frame = icon.ico.getimage(size).convert("RGBA")
                if (
                    frame.getpixel((0, 0)) != background
                    or frame.getchannel("A").getextrema() != (255, 255)
                ):
                    raise ValueError(f"Incorrect ICO background: {size}")

        manifest = {
            "name": "Wren",
            "short_name": "Wren",
            "icons": [
                {
                    "src": f"/android-chrome-{size}x{size}.png",
                    "sizes": f"{size}x{size}",
                    "type": "image/png",
                }
                for size in (192, 512)
            ],
            "theme_color": colors["background"],
            "background_color": colors["background"],
            "start_url": "/",
            "display": "standalone",
        }
        (staging / "site.webmanifest").write_text(json.dumps(manifest, indent=2) + "\n")
        filenames = ["favicon.svg", *PNG_SIZES, "favicon.ico", "site.webmanifest"]
        for output in args.output_dir:
            output.mkdir(parents=True, exist_ok=True)
            # Stage on the destination filesystem so each replacement is atomic.
            with tempfile.TemporaryDirectory(prefix=".favicons-", dir=output) as directory:
                local_staging = Path(directory)
                for filename in filenames:
                    shutil.copyfile(staging / filename, local_staging / filename)
                for filename in filenames:
                    (local_staging / filename).replace(output / filename)
            print(f"Generated {len(filenames)} favicon assets in {output}")


if __name__ == "__main__":
    main()
