import base64
import builtins
import io
import struct
import unittest
import zlib
from unittest.mock import patch

from PIL import Image, ImageFile

from support import load_engine


def raster(fmt="PNG", size=(120, 32)):
    buffer = io.BytesIO()
    Image.new("RGB", size, (24, 64, 136)).save(buffer, format=fmt)
    return buffer.getvalue()


def uri(data, mime="png"):
    return "data:image/" + mime + ";base64," + base64.b64encode(data).decode("ascii")


class BrandingTests(unittest.TestCase):
    def setUp(self):
        self.e = load_engine()

    def test_default_empty_logo_does_not_import_pillow(self):
        original = builtins.__import__
        def guarded(name, *args, **kwargs):
            if name == "PIL" or name.startswith("PIL."):
                raise AssertionError("Default empty logo must not import Pillow.")
            return original(name, *args, **kwargs)
        with patch("builtins.__import__", side_effect=guarded):
            self.e.validate_logo("")

    def test_complete_png_jpeg_mime_and_alt(self):
        self.e.validate_logo(uri(raster()), "CLIENTE")
        self.e.validate_logo(uri(raster("JPEG"), "jpeg"), "CLIENTE")
        for value in ("", None, "x" * 121, "bad\nalt", "\x7f"):
            with self.subTest(value=value), self.assertRaises(self.e.EvidenceError):
                self.e.validate_logo(uri(raster()), value)
        with self.assertRaises(self.e.EvidenceError):
            self.e.validate_logo(uri(raster("JPEG"), "png"))

    def test_100kb_2048_dimension_bounds_and_single_frame(self):
        self.e.validate_logo(uri(raster(size=(2048, 8))), "CLIENTE")
        for data in (raster(size=(2049, 8)), raster() + b"x" * 100001):
            with self.assertRaises(self.e.EvidenceError):
                self.e.validate_logo(uri(data), "CLIENTE")
        animated = io.BytesIO()
        Image.new("RGB", (16, 16), (0, 0, 0)).save(animated, format="PNG", save_all=True,
            append_images=[Image.new("RGB", (16, 16), (255, 255, 255))], duration=100, loop=0)
        with self.assertRaises(self.e.EvidenceError):
            self.e.validate_logo(uri(animated.getvalue()), "CLIENTE")

    def test_corrupt_idat_with_valid_crc_is_rejected_by_actual_decode(self):
        data = raster()
        position = 8
        chunks = [data[:8]]
        while position < len(data):
            length = struct.unpack(">I", data[position:position + 4])[0]
            kind = data[position + 4:position + 8]
            original = data[position + 8:position + 8 + length]
            content = b"not-a-deflate-stream" if kind == b"IDAT" else original
            chunks.append(struct.pack(">I", len(content)) + kind + content + struct.pack(">I", zlib.crc32(kind + content) & 0xffffffff))
            position += 12 + length
        invalid = b"".join(chunks)
        with Image.open(io.BytesIO(invalid)) as image:
            image.verify()
        with self.assertRaises(self.e.EvidenceError) as raised:
            self.e.validate_logo(uri(invalid), "CLIENTE")
        self.assertEqual(raised.exception.code, "invalid_logo")

    def test_truncated_jpeg_and_permissive_decoder_settings_fail_closed(self):
        data = raster("JPEG", (64, 64))
        marker = data.index(b"\xff\xda")
        header_end = marker + 2 + int.from_bytes(data[marker + 2:marker + 4], "big")
        invalid = data[:header_end + 2]
        with self.assertRaises(self.e.EvidenceError):
            self.e.validate_logo(uri(invalid, "jpeg"), "CLIENTE")
        with patch.object(ImageFile, "LOAD_TRUNCATED_IMAGES", True), self.assertRaises(self.e.EvidenceError) as raised:
            self.e.validate_logo(uri(data, "jpeg"), "CLIENTE")
        self.assertEqual(raised.exception.code, "unsafe_decoder_settings")

    def test_invalid_logo_stops_before_identity_or_collection(self):
        with patch.object(self.e, "CLIENT_LOGO_DATA_URI", uri(b"invalid")), patch.object(self.e, "Identity") as identity:
            result = self.e.main()
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "invalid_logo")
        identity.assert_not_called()


if __name__ == "__main__":
    unittest.main()
