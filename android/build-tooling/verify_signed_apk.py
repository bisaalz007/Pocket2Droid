#!/usr/bin/env python3
"""Verify a signed Pocket2Droid V6.52 development APK.

Usage:
  python3 verify_signed_apk.py signed.apk expected_native_sha256

Requires Python cryptography.
"""

import hashlib
import struct
import sys
import zipfile
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding


APK_SIGNATURE_ALGORITHM = 0x0103
APK_SIGNATURE_V2_ID = 0x7109871A
APK_SIGNATURE_MAGIC = b"APK Sig Block 42"
DIGEST_CHUNK_SIZE = 1024 * 1024

EXPECTED_CERT_SHA256 = (
    "85d6f87a557def48710b8e295ed58513888a99852843a90106b3b7f18e39681b"
)
EXPECTED_PACKAGE = "com.samsixx.wm6android"
EXPECTED_VERSION_CODE = 652
EXPECTED_VERSION_NAME = "6.52"
EXPECTED_MIN_SDK = 23
EXPECTED_TARGET_SDK = 36


def u16(data, offset):
    return struct.unpack_from("<H", data, offset)[0]


def u32(data, offset):
    return struct.unpack_from("<I", data, offset)[0]


def u64(data, offset):
    return struct.unpack_from("<Q", data, offset)[0]


def read_length_prefixed(data, offset):
    length = u32(data, offset)
    offset += 4
    end = offset + length
    if end > len(data):
        raise ValueError("length-prefixed field exceeds container")
    return data[offset:end], end


def find_eocd(data):
    offset = data.rfind(b"PK\x05\x06", max(0, len(data) - 65557))
    if offset < 0 or offset + 22 > len(data):
        raise ValueError("EOCD missing")
    fields = struct.unpack_from("<4sHHHHIIH", data, offset)
    central_directory_size = fields[5]
    central_directory_offset = fields[6]
    comment_length = fields[7]
    if offset + 22 + comment_length != len(data):
        raise ValueError("EOCD mismatch")
    return offset, central_directory_size, central_directory_offset


def locate_signature_block(data, central_directory_offset):
    if data[central_directory_offset - 16:central_directory_offset] != APK_SIGNATURE_MAGIC:
        raise ValueError("APK Signature Scheme v2 block missing")
    second_size = u64(data, central_directory_offset - 24)
    start = central_directory_offset - (second_size + 8)
    if start < 0 or u64(data, start) != second_size:
        raise ValueError("APK signing-block size mismatch")
    return start, central_directory_offset


def calculate_content_digest(data, signature_start, central_directory_offset, eocd_offset):
    eocd = bytearray(data[eocd_offset:])
    struct.pack_into("<I", eocd, 16, signature_start)
    chunk_digests = []
    parts = (
        data[:signature_start],
        data[central_directory_offset:eocd_offset],
        bytes(eocd),
    )
    for part in parts:
        for offset in range(0, len(part), DIGEST_CHUNK_SIZE):
            chunk = part[offset:offset + DIGEST_CHUNK_SIZE]
            chunk_digests.append(
                hashlib.sha256(
                    b"\xA5" + struct.pack("<I", len(chunk)) + chunk
                ).digest()
            )
    return hashlib.sha256(
        b"\x5A" + struct.pack("<I", len(chunk_digests)) + b"".join(chunk_digests)
    ).digest()


def parse_v2_signature(data, start, end):
    offset = start + 8
    pairs_end = end - 24
    value = None
    while offset < pairs_end:
        pair_length = u64(data, offset)
        offset += 8
        pair_id = u32(data, offset)
        pair_end = offset + pair_length
        if pair_end > pairs_end or pair_length < 4:
            raise ValueError("invalid APK signing-block pair")
        if pair_id == APK_SIGNATURE_V2_ID:
            value = data[offset + 4:pair_end]
        offset = pair_end
    if value is None:
        raise ValueError("APK Signature Scheme v2 pair missing")

    signers, _ = read_length_prefixed(value, 0)
    signer, _ = read_length_prefixed(signers, 0)
    signed_data, offset = read_length_prefixed(signer, 0)
    signatures, offset = read_length_prefixed(signer, offset)
    _public_key, _ = read_length_prefixed(signer, offset)

    digests, offset = read_length_prefixed(signed_data, 0)
    certificates, offset = read_length_prefixed(signed_data, offset)
    _attributes, _ = read_length_prefixed(signed_data, offset)

    digest_record, _ = read_length_prefixed(digests, 0)
    digest_algorithm = u32(digest_record, 0)
    expected_digest, _ = read_length_prefixed(digest_record, 4)

    signature_record, _ = read_length_prefixed(signatures, 0)
    signature_algorithm = u32(signature_record, 0)
    signature, _ = read_length_prefixed(signature_record, 4)
    certificate_der, _ = read_length_prefixed(certificates, 0)

    return (
        digest_algorithm,
        expected_digest,
        signature_algorithm,
        signature,
        certificate_der,
        signed_data,
    )


def read_utf8_length(data, offset):
    first = data[offset]
    offset += 1
    if first & 0x80:
        return ((first & 0x7F) << 8) | data[offset], offset + 1
    return first, offset


def parse_string_pool(chunk):
    header_size = u16(chunk, 2)
    string_count = u32(chunk, 8)
    flags = u32(chunk, 16)
    strings_start = u32(chunk, 20)
    utf8 = bool(flags & 0x100)
    offsets = [u32(chunk, header_size + 4 * index) for index in range(string_count)]
    strings = []
    for string_offset in offsets:
        offset = strings_start + string_offset
        if utf8:
            _, offset = read_utf8_length(chunk, offset)
            byte_length, offset = read_utf8_length(chunk, offset)
            strings.append(chunk[offset:offset + byte_length].decode("utf-8"))
        else:
            length = u16(chunk, offset)
            offset += 2
            strings.append(chunk[offset:offset + 2 * length].decode("utf-16le"))
    return strings


def parse_manifest(manifest):
    strings = None
    elements = []
    offset = 8
    while offset < len(manifest):
        chunk_type = u16(manifest, offset)
        chunk_size = u32(manifest, offset + 4)
        if chunk_size <= 0 or offset + chunk_size > len(manifest):
            raise ValueError("invalid binary manifest chunk")
        chunk = manifest[offset:offset + chunk_size]
        if chunk_type == 0x0001:
            strings = parse_string_pool(chunk)
        elif chunk_type == 0x0102:
            if strings is None:
                raise ValueError("manifest element precedes string pool")
            name = strings[u32(chunk, 20)]
            attribute_start = u16(chunk, 24)
            attribute_size = u16(chunk, 26)
            attribute_count = u16(chunk, 28)
            base = 16 + attribute_start
            attributes = {}
            for index in range(attribute_count):
                attribute = base + index * attribute_size
                name_index = u32(chunk, attribute + 4)
                data_type = chunk[attribute + 15]
                value = u32(chunk, attribute + 16)
                attributes[strings[name_index]] = strings[value] if data_type == 3 else value
            elements.append((name, attributes))
        offset += chunk_size
    return elements


def verify(apk_path, expected_native_sha256):
    data = apk_path.read_bytes()
    eocd_offset, central_directory_size, central_directory_offset = find_eocd(data)
    if central_directory_offset + central_directory_size != eocd_offset:
        raise ValueError("unexpected central-directory layout")

    signature_start, signature_end = locate_signature_block(
        data, central_directory_offset
    )
    (
        digest_algorithm,
        recorded_digest,
        signature_algorithm,
        signature,
        certificate_der,
        signed_data,
    ) = parse_v2_signature(data, signature_start, signature_end)

    if digest_algorithm != APK_SIGNATURE_ALGORITHM or signature_algorithm != APK_SIGNATURE_ALGORITHM:
        raise SystemExit("v2_signature_algorithm=FAIL")
    calculated_digest = calculate_content_digest(
        data, signature_start, central_directory_offset, eocd_offset
    )
    if recorded_digest != calculated_digest:
        raise SystemExit("v2_content_digest_match=FAIL")

    certificate = x509.load_der_x509_certificate(certificate_der)
    certificate.public_key().verify(
        signature, signed_data, padding.PKCS1v15(), hashes.SHA256()
    )
    certificate_sha256 = hashlib.sha256(certificate_der).hexdigest()
    if certificate_sha256 != EXPECTED_CERT_SHA256:
        raise SystemExit("signer_certificate=FAIL")

    with zipfile.ZipFile(apk_path) as archive:
        if archive.testzip() is not None:
            raise SystemExit("apk_integrity=FAIL")
        manifest = archive.read("AndroidManifest.xml")
        native = archive.read("lib/arm64-v8a/libwm6android.so")
        names = archive.namelist()

    elements = parse_manifest(manifest)
    by_name = {}
    for name, attributes in elements:
        by_name.setdefault(name, []).append(attributes)
    manifest_attributes = by_name["manifest"][0]
    sdk_attributes = by_name["uses-sdk"][0]

    if manifest_attributes.get("package") != EXPECTED_PACKAGE:
        raise SystemExit("package=FAIL")
    if (
        manifest_attributes.get("versionCode") != EXPECTED_VERSION_CODE
        or manifest_attributes.get("versionName") != EXPECTED_VERSION_NAME
    ):
        raise SystemExit("version=FAIL")
    if (
        sdk_attributes.get("minSdkVersion") != EXPECTED_MIN_SDK
        or sdk_attributes.get("targetSdkVersion") != EXPECTED_TARGET_SDK
    ):
        raise SystemExit("sdk=FAIL")

    native_sha256 = hashlib.sha256(native).hexdigest()
    if native_sha256 != expected_native_sha256:
        raise SystemExit("apk_native=FAIL")

    print("apk_sha256=" + hashlib.sha256(data).hexdigest())
    print("v2_signature_verified=1")
    print("v2_content_digest_match=1")
    print("cert_sha256=" + certificate_sha256)
    print("package=" + manifest_attributes["package"])
    print("versionCode=" + str(manifest_attributes["versionCode"]))
    print("versionName=" + manifest_attributes["versionName"])
    print("minSdk=" + str(sdk_attributes["minSdkVersion"]))
    print("targetSdk=" + str(sdk_attributes["targetSdkVersion"]))
    print("native_sha256=" + native_sha256)
    print("entries=" + ",".join(names))


def main():
    if len(sys.argv) != 3:
        raise SystemExit(
            "usage: verify_signed_apk.py signed.apk expected_native_sha256"
        )
    expected_native_sha256 = sys.argv[2].strip().lower()
    if len(expected_native_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in expected_native_sha256
    ):
        raise SystemExit("invalid expected native SHA-256")
    verify(Path(sys.argv[1]), expected_native_sha256)


if __name__ == "__main__":
    main()
