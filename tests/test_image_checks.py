import base64
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from claude_session_image_audit.cli import _inspect_image, main


def block(data, media_type="image/png"):
    return {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}}


class ImageChecks(unittest.TestCase):
    def test_signatures_and_base64_are_independent(self):
        png = base64.b64encode(b"\x89PNG\r\n\x1a\nfictional").decode()
        self.assertEqual(_inspect_image(png, "image/png"), set())
        self.assertEqual(_inspect_image(png, "image/jpeg"), {"signature_mismatch"})
        self.assertEqual(_inspect_image("abc!", "image/png"), {"invalid_base64"})
        self.assertEqual(_inspect_image(None, None), {"missing_data", "media_type"})
        self.assertEqual(_inspect_image(png, []), {"media_type"})

    def test_base64_validation_crosses_chunk_boundary(self):
        data = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"x" * 60000).decode()
        self.assertEqual(_inspect_image(data, "image/png"), set())
        broken = data[:65536] + "!" + data[65537:]
        self.assertEqual(_inspect_image(broken, "image/png"), {"invalid_base64"})
        self.assertEqual(_inspect_image("AA==" + "AAAA" * 20000, "image/png"), {"invalid_base64"})

    def test_supported_signatures_and_non_ascii(self):
        for media_type, raw in (
            ("image/jpeg", b"\xff\xd8\xffsynthetic"),
            ("image/gif", b"GIF89asynthetic"),
            ("image/webp", b"RIFFxxxxWEBPsynthetic"),
        ):
            with self.subTest(media_type=media_type):
                self.assertEqual(_inspect_image(base64.b64encode(raw).decode(), media_type), set())
        self.assertEqual(_inspect_image("你好", "image/png"), {"invalid_base64"})

    def test_read_only_cli_checks_and_default_compatibility(self):
        png = base64.b64encode(b"\x89PNG\r\n\x1a\nfictional").decode()
        missing = {"type": "image", "source": {"type": "base64", "media_type": "image/png"}}
        records = [block(png), block("secret-not-base64!"), missing, block(png, "image/jpeg")]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.jsonl"
            original = "\n".join(json.dumps(x) for x in records) + "\n"
            path.write_text(original)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(main([str(path), "--format", "json", "--check-images"]), 0)
            rendered = out.getvalue()
            self.assertNotIn("secret-not-base64", rendered)
            self.assertNotIn(png, rendered)
            result = json.loads(rendered)
            self.assertEqual(result["image_checks"], {
                "blocks_checked": 4, "blocks_with_findings": 3,
                "missing_data": 1, "invalid_base64": 1,
                "media_type": 0, "signature_mismatch": 1,
            })
            self.assertEqual(path.read_text(), original)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(main([str(path), "--format", "json"]), 0)
            self.assertNotIn("image_checks", json.loads(out.getvalue()))

    def test_missing_data_is_shown_even_when_no_images_counted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.jsonl"
            path.write_text(json.dumps({"type": "image", "source": {"type": "base64"}}))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(main([str(path), "--lang", "zh", "--check-images"]), 0)
            self.assertIn("缺少数据 1", out.getvalue())
            self.assertIn("synthetic.jsonl: missing_data=1", out.getvalue())


if __name__ == "__main__":
    unittest.main()
