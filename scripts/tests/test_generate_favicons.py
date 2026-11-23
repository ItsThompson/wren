# ruff: noqa: PT009
# Use stdlib unittest in the generator's isolated environment.

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree

from coloraide import Color
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / "scripts/generate_favicons.py"
SVG_NAMESPACE = "{http://www.w3.org/2000/svg}"


class GenerateFaviconsTest(unittest.TestCase):
    def test_generates_matching_opaque_packages_from_the_shared_theme(self):
        theme = (ROOT / "shared/theme/tokens.css").read_text()
        colors = {}
        for name in ("background", "primary"):
            match = re.search(rf"--{name}:\s*([^;]+);", theme)
            self.assertIsNotNone(match)
            colors[name] = Color(match[1]).convert("srgb").to_string(hex=True)
        background = (*bytes.fromhex(colors["background"][1:]), 255)
        primary = (*bytes.fromhex(colors["primary"][1:]), 255)
        source = ElementTree.parse(  # noqa: S314  # Trusted repository artwork.
            ROOT / "shared/branding/icon.svg"
        )
        original_path = source.find(f".//{SVG_NAMESPACE}path").get("d")

        with tempfile.TemporaryDirectory() as directory:
            outputs = [Path(directory) / "app", Path(directory) / "docs"]
            result = subprocess.run(  # noqa: S603  # Repository script, no shell.
                [sys.executable, str(GENERATOR), "--output-dir", *map(str, outputs)],
                cwd=directory,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            expected_sizes = {
                "favicon-16x16.png": 16,
                "favicon-32x32.png": 32,
                "apple-touch-icon.png": 180,
                "android-chrome-192x192.png": 192,
                "android-chrome-512x512.png": 512,
            }
            expected_files = {*expected_sizes, "favicon.svg", "favicon.ico", "site.webmanifest"}
            for output in outputs:
                self.assertEqual({path.name for path in output.iterdir()}, expected_files)
                svg = ElementTree.parse(output / "favicon.svg")  # noqa: S314  # Generated test asset.
                self.assertEqual(svg.find(f".//{SVG_NAMESPACE}path").get("d"), original_path)
                self.assertEqual(svg.find(f".//{SVG_NAMESPACE}path").get("fill"), colors["primary"])
                self.assertEqual(svg.find(f"{SVG_NAMESPACE}rect").get("fill"), colors["background"])
                self.assertEqual(svg.find(f"{SVG_NAMESPACE}title").text, "Wren")
                for filename, size in expected_sizes.items():
                    with Image.open(output / filename) as image:
                        rgba = image.convert("RGBA")
                        self.assertEqual(image.size, (size, size))
                        self.assertEqual(rgba.getchannel("A").getextrema(), (255, 255))
                        for corner in ((0, 0), (size - 1, 0), (0, size - 1), (size - 1, size - 1)):
                            self.assertEqual(rgba.getpixel(corner), background)
                        # The offset opening stays cream, while the left body stays terracotta.
                        opening = (round(size * 55 / 96), round(size * 43 / 96))
                        self.assertEqual(rgba.getpixel(opening), background)
                        self.assertEqual(rgba.getpixel((round(size * 24 / 96), size // 2)), primary)
                with Image.open(output / "favicon.ico") as icon:
                    self.assertEqual(icon.ico.sizes(), {(16, 16), (32, 32), (48, 48)})
                    for size in icon.ico.sizes():
                        frame = icon.ico.getimage(size).convert("RGBA")
                        self.assertEqual(frame.getchannel("A").getextrema(), (255, 255))
                        self.assertEqual(frame.getpixel((0, 0)), background)
                manifest = json.loads((output / "site.webmanifest").read_text())
                self.assertEqual(manifest["name"], "Wren")
                self.assertEqual(manifest["background_color"], colors["background"])
                self.assertEqual(manifest["theme_color"], colors["background"])
                self.assertEqual(
                    {icon["sizes"] for icon in manifest["icons"]}, {"192x192", "512x512"}
                )
                for icon in manifest["icons"]:
                    self.assertTrue((output / icon["src"].lstrip("/")).is_file())
            for filename in expected_files:
                self.assertEqual(
                    (outputs[0] / filename).read_bytes(), (outputs[1] / filename).read_bytes()
                )

    def test_invalid_source_preserves_existing_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "public"
            output.mkdir()
            existing = output / "favicon.ico"
            existing.write_bytes(b"existing icon")
            invalid_source = Path(directory) / "invalid.svg"
            invalid_source.write_text("not SVG")
            result = subprocess.run(  # noqa: S603  # Repository script, no shell.
                [
                    sys.executable, str(GENERATOR), "--source", str(invalid_source),
                    "--output-dir", str(output),
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("ParseError", result.stderr)
            self.assertEqual(existing.read_bytes(), b"existing icon")
            self.assertEqual(list(output.iterdir()), [existing])

    def test_failed_image_validation_preserves_existing_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "public"
            output.mkdir()
            existing = output / "favicon.ico"
            existing.write_bytes(b"existing icon")
            oversized_source = Path(directory) / "oversized.svg"
            artwork = (ROOT / "shared/branding/icon.svg").read_text()
            oversized_source.write_text(
                artwork.replace('viewBox="0 0 96 96"', 'viewBox="0 0 192 192"')
            )
            result = subprocess.run(  # noqa: S603  # Repository script, no shell.
                [
                    sys.executable, str(GENERATOR), "--source", str(oversized_source),
                    "--output-dir", str(output),
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Incorrect dimensions or transparent pixels", result.stderr)
            self.assertEqual(existing.read_bytes(), b"existing icon")
            self.assertEqual(list(output.iterdir()), [existing])


if __name__ == "__main__":
    unittest.main()
