"""Preflight bounds must apply before ZipFile allocates directory objects."""
import io
import struct
import sys
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from previews import _zip_directory_limit, PreviewUnavailable


def archive_bytes(count=2, comment=b''):
    target = io.BytesIO()
    with zipfile.ZipFile(target, 'w') as archive:
        for number in range(count):
            archive.writestr(f'page{number}.png', b'generated fixture')
        archive.comment = comment
    return target.getvalue()


class ZipLimitTests(unittest.TestCase):
    def test_valid_plain_prefixed_and_commented_directory(self):
        for prefix in (b'', b'generated self-extracting prefix'):
            for comment in (b'', b'generated comment'):
                source = io.BytesIO(prefix + archive_bytes(comment=comment))
                _zip_directory_limit(source)
                self.assertEqual(source.tell(), 0)
                with zipfile.ZipFile(source) as archive:
                    self.assertEqual(len(archive.infolist()), 2)

    def test_forged_small_entry_count_is_rejected(self):
        raw = bytearray(archive_bytes())
        end = raw.rfind(b'PK\x05\x06')
        struct.pack_into('<2H', raw, end + 8, 1, 1)
        with self.assertRaises(PreviewUnavailable): _zip_directory_limit(io.BytesIO(raw))

    def test_actual_directory_over_count_limit_is_rejected(self):
        raw = bytearray(archive_bytes(10001))
        end = raw.rfind(b'PK\x05\x06')
        struct.pack_into('<2H', raw, end + 8, 1, 1)
        with self.assertRaises(PreviewUnavailable): _zip_directory_limit(io.BytesIO(raw))

    def test_zip64_locator_without_legacy_sentinels_is_rejected(self):
        raw = archive_bytes()
        end = raw.rfind(b'PK\x05\x06')
        count = struct.unpack_from('<H', raw, end + 10)[0]
        size, offset = struct.unpack_from('<2I', raw, end + 12)
        record = struct.pack('<4sQ2H2I4Q', b'PK\x06\x06', 44, 45, 45, 0, 0, count, count, size, offset)
        locator = struct.pack('<4sIQI', b'PK\x06\x07', 0, end, 1)
        hidden_zip64 = raw[:end] + record + locator + raw[end:]
        # Confirms this really is a ZIP64 record accepted by the stdlib, even
        # though the ordinary EOCD count/size are small and look harmless.
        with zipfile.ZipFile(io.BytesIO(hidden_zip64)) as archive:
            self.assertEqual(len(archive.infolist()), 2)
        with self.assertRaises(PreviewUnavailable): _zip_directory_limit(io.BytesIO(hidden_zip64))

    def test_directory_lengths_and_signature_must_fit(self):
        for bad_signature in (False, True):
            raw = bytearray(archive_bytes())
            first = raw.index(b'PK\x01\x02')
            if bad_signature: raw[first] = 0
            else: struct.pack_into('<H', raw, first + 28, 65535)
            with self.assertRaises(PreviewUnavailable): _zip_directory_limit(io.BytesIO(raw))

    def test_per_entry_zip64_and_multidisk_rejected(self):
        for field_offset, fmt, value in ((20, '<I', 0xffffffff), (24, '<I', 0xffffffff),
                                         (42, '<I', 0xffffffff), (34, '<H', 1)):
            raw = bytearray(archive_bytes())
            first = raw.index(b'PK\x01\x02')
            struct.pack_into(fmt, raw, first + field_offset, value)
            with self.assertRaises(PreviewUnavailable): _zip_directory_limit(io.BytesIO(raw))

    def test_preflight_never_constructs_zipinfo(self):
        source = io.BytesIO(archive_bytes())
        with patch.object(zipfile, 'ZipInfo', side_effect=AssertionError('allocated ZipInfo')):
            _zip_directory_limit(source)


if __name__ == '__main__': unittest.main()
