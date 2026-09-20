#!/usr/bin/env python3
"""Convert local images to JPG while setting a target DPI."""

from __future__ import annotations

import argparse
import shutil
import struct
import subprocess
import sys
import tempfile
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DPI = 96
DEFAULT_QUALITY = 95
OUTPUT_SUFFIX = ".jpg"
DEFAULT_EXTENSIONS = {
    ".avif",
    ".bmp",
    ".dds",
    ".dib",
    ".exr",
    ".gif",
    ".heic",
    ".heics",
    ".heif",
    ".heifs",
    ".icns",
    ".ico",
    ".j2k",
    ".jfi",
    ".jfif",
    ".jif",
    ".jp2",
    ".jpeg",
    ".jpg",
    ".jpf",
    ".jpm",
    ".jpx",
    ".jxl",
    ".pbm",
    ".pgm",
    ".png",
    ".ppm",
    ".psd",
    ".tga",
    ".tif",
    ".tiff",
    ".webp",
}
FIRST_FRAME_EXTENSIONS = {
    ".avif",
    ".gif",
    ".heic",
    ".heics",
    ".heif",
    ".heifs",
    ".tif",
    ".tiff",
    ".webp",
}


@dataclass(frozen=True)
class ConversionTask:
    src: Path
    dst: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Convert a local image file or every supported image in a directory tree "
            "into JPG while writing target DPI metadata."
        )
    )
    parser.add_argument(
        "--input-path",
        type=Path,
        required=True,
        help="Source file or source directory.",
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        required=True,
        help="Destination JPG file path or destination directory.",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=DEFAULT_DPI,
        help=f"Target JPG DPI metadata (default: {DEFAULT_DPI}).",
    )
    parser.add_argument(
        "--quality",
        type=int,
        default=DEFAULT_QUALITY,
        help=f"JPG quality from 1 to 100 (default: {DEFAULT_QUALITY}).",
    )
    parser.add_argument(
        "--backend",
        choices=("auto", "magick", "sips"),
        default="auto",
        help="Conversion backend. auto prefers ImageMagick, then macOS sips.",
    )
    parser.add_argument(
        "--extra-extension",
        action="append",
        default=[],
        help="Additional file extension to include during directory scans, for example .cr2.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing output JPG files.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print the planned conversions.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional maximum number of files to process.",
    )
    return parser.parse_args()


def normalize_extension(value: str) -> str:
    normalized = value.strip().lower()
    if not normalized:
        raise ValueError("empty extension")
    if not normalized.startswith("."):
        normalized = f".{normalized}"
    return normalized


def validate_args(args: argparse.Namespace) -> None:
    if args.dpi <= 0:
        raise ValueError("--dpi must be greater than 0")
    if args.dpi > 65535:
        raise ValueError("--dpi must be 65535 or less")
    if not 1 <= args.quality <= 100:
        raise ValueError("--quality must be between 1 and 100")
    if args.limit is not None and args.limit < 0:
        raise ValueError("--limit must be 0 or greater")
    for extension in args.extra_extension:
        normalize_extension(extension)


def choose_backend(requested: str) -> str:
    magick = shutil.which("magick")
    sips = shutil.which("sips")

    if requested == "auto":
        if magick:
            return "magick"
        if sips:
            return "sips"
    elif requested == "magick" and magick:
        return "magick"
    elif requested == "sips" and sips:
        return "sips"

    if requested == "auto":
        raise RuntimeError("No supported backend found. Install ImageMagick (`magick`) or use macOS `sips`.")
    raise RuntimeError(f"Requested backend is unavailable: {requested}")


def collect_extensions(extra_extensions: list[str]) -> set[str]:
    extensions = set(DEFAULT_EXTENSIONS)
    for extension in extra_extensions:
        extensions.add(normalize_extension(extension))
    return extensions


def collect_sources(input_path: Path, extensions: set[str], limit: int | None) -> list[Path]:
    if input_path.is_file():
        if limit == 0:
            return []
        return [input_path]

    sources = sorted(
        path
        for path in input_path.rglob("*")
        if path.is_file() and path.suffix.lower() in extensions
    )
    if limit is not None:
        return sources[:limit]
    return sources


def resolve_single_output(src: Path, output_path: Path) -> Path:
    if output_path.exists():
        if output_path.is_dir():
            return output_path / f"{src.stem}{OUTPUT_SUFFIX}"
        if output_path.suffix.lower() not in {".jpg", ".jpeg"}:
            raise ValueError("Single-file output paths must end with .jpg or .jpeg.")
        return output_path

    if output_path.suffix:
        if output_path.suffix.lower() not in {".jpg", ".jpeg"}:
            raise ValueError("Single-file output paths must end with .jpg or .jpeg.")
        return output_path

    return output_path / f"{src.stem}{OUTPUT_SUFFIX}"


def build_tasks(input_path: Path, output_path: Path, extensions: set[str], limit: int | None) -> list[ConversionTask]:
    sources = collect_sources(input_path, extensions, limit)
    if input_path.is_file():
        if not sources:
            return []
        return [ConversionTask(src=sources[0], dst=resolve_single_output(sources[0], output_path))]

    if output_path.exists() and not output_path.is_dir():
        raise ValueError("Directory input requires --output-path to be a directory.")
    if not output_path.exists() and output_path.suffix.lower() in {".jpg", ".jpeg"}:
        raise ValueError("Directory input requires --output-path to be a directory, not a JPG file path.")

    tasks: list[ConversionTask] = []
    seen_destinations: dict[str, Path] = {}
    for src in sources:
        rel = src.relative_to(input_path)
        dst = (output_path / rel).with_suffix(OUTPUT_SUFFIX)
        key = str(dst.resolve(strict=False))
        previous = seen_destinations.get(key)
        if previous is not None and previous != src:
            raise ValueError(f"Destination collision: {previous} and {src} would both write {dst}")
        seen_destinations[key] = src
        tasks.append(ConversionTask(src=src, dst=dst))
    return tasks


def build_magick_command(src: Path, dst: Path, dpi: int, quality: int) -> list[str]:
    src_arg = str(src)
    if src.suffix.lower() in FIRST_FRAME_EXTENSIONS:
        src_arg = f"{src_arg}[0]"

    return [
        "magick",
        src_arg,
        "-auto-orient",
        "-background",
        "white",
        "-alpha",
        "remove",
        "-alpha",
        "off",
        "-quality",
        str(quality),
        "-units",
        "PixelsPerInch",
        "-density",
        str(dpi),
        str(dst),
    ]


def build_sips_command(src: Path, dst: Path, dpi: int, quality: int) -> list[str]:
    return [
        "sips",
        "-s",
        "format",
        "jpeg",
        "-s",
        "formatOptions",
        str(quality),
        "-s",
        "dpiWidth",
        str(dpi),
        "-s",
        "dpiHeight",
        str(dpi),
        str(src),
        "--out",
        str(dst),
    ]


def run_command(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode == 0:
        return

    detail = result.stderr.strip() or result.stdout.strip() or "unknown conversion error"
    raise RuntimeError(detail)


def iter_jpeg_segments(data: bytes) -> Generator[tuple[int, int, int, int], None, None]:
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        raise ValueError("Not a JPEG file")

    pos = 2
    while pos + 4 <= len(data):
        if data[pos] != 0xFF:
            raise ValueError("Invalid JPEG marker stream")

        while pos < len(data) and data[pos] == 0xFF:
            pos += 1
        if pos >= len(data):
            break

        marker = data[pos]
        pos += 1
        if marker == 0xD9:
            break
        if marker == 0xDA:
            if pos + 2 > len(data):
                raise ValueError("Truncated JPEG scan header")
            length = int.from_bytes(data[pos : pos + 2], "big")
            segment_end = pos + length
            if segment_end > len(data):
                raise ValueError("Truncated JPEG scan header")
            yield marker, pos - 2, pos + 2, segment_end
            break
        if 0xD0 <= marker <= 0xD7 or marker == 0x01:
            continue

        if pos + 2 > len(data):
            raise ValueError("Truncated JPEG segment length")

        length = int.from_bytes(data[pos : pos + 2], "big")
        segment_end = pos + length
        if segment_end > len(data):
            raise ValueError("Truncated JPEG segment")
        yield marker, pos - 2, pos + 2, segment_end
        pos = segment_end


def build_jfif_segment(dpi: int) -> bytes:
    payload = b"JFIF\x00\x01\x01\x01" + struct.pack(">HHBB", dpi, dpi, 0, 0)
    return b"\xff\xe0" + struct.pack(">H", len(payload) + 2) + payload


def patch_jfif_density(data: bytearray, dpi: int) -> None:
    for marker, _, payload_start, segment_end in iter_jpeg_segments(data):
        if marker != 0xE0:
            continue
        if segment_end - payload_start < 14:
            continue
        if data[payload_start : payload_start + 5] != b"JFIF\x00":
            continue
        data[payload_start + 7] = 1
        data[payload_start + 8 : payload_start + 10] = struct.pack(">H", dpi)
        data[payload_start + 10 : payload_start + 12] = struct.pack(">H", dpi)
        return

    data[2:2] = build_jfif_segment(dpi)


def patch_exif_resolution(data: bytearray, dpi: int) -> None:
    for marker, _, payload_start, segment_end in iter_jpeg_segments(data):
        if marker != 0xE1:
            continue
        if segment_end - payload_start < 14:
            continue
        if data[payload_start : payload_start + 6] != b"Exif\x00\x00":
            continue

        tiff_start = payload_start + 6
        byte_order = bytes(data[tiff_start : tiff_start + 2])
        if byte_order == b"II":
            endian = "<"
        elif byte_order == b"MM":
            endian = ">"
        else:
            continue

        if struct.unpack_from(f"{endian}H", data, tiff_start + 2)[0] != 42:
            continue

        ifd0_offset = struct.unpack_from(f"{endian}I", data, tiff_start + 4)[0]
        ifd0_start = tiff_start + ifd0_offset
        if ifd0_start + 2 > segment_end:
            continue

        entry_count = struct.unpack_from(f"{endian}H", data, ifd0_start)[0]
        for index in range(entry_count):
            entry_start = ifd0_start + 2 + index * 12
            if entry_start + 12 > segment_end:
                break

            tag, field_type, count = struct.unpack_from(f"{endian}HHI", data, entry_start)
            value_start = entry_start + 8
            if tag in {0x011A, 0x011B} and field_type == 5 and count == 1:
                rational_offset = struct.unpack_from(f"{endian}I", data, value_start)[0]
                rational_start = tiff_start + rational_offset
                if rational_start + 8 > segment_end:
                    continue
                struct.pack_into(f"{endian}II", data, rational_start, dpi, 1)
            elif tag == 0x0128 and field_type == 3 and count == 1:
                struct.pack_into(f"{endian}H", data, value_start, 2)
                data[value_start + 2 : value_start + 4] = b"\x00\x00"
        return


def set_jpeg_dpi(path: Path, dpi: int) -> None:
    data = bytearray(path.read_bytes())
    patch_jfif_density(data, dpi)
    patch_exif_resolution(data, dpi)
    path.write_bytes(data)


def convert_image(task: ConversionTask, backend: str, dpi: int, quality: int) -> None:
    with tempfile.NamedTemporaryFile(
        prefix=f"{task.dst.stem}.",
        suffix=OUTPUT_SUFFIX,
        dir=task.dst.parent,
        delete=False,
    ) as handle:
        temp_path = Path(handle.name)

    try:
        if backend == "magick":
            run_command(build_magick_command(task.src, temp_path, dpi, quality))
        else:
            run_command(build_sips_command(task.src, temp_path, dpi, quality))
        set_jpeg_dpi(temp_path, dpi)
        temp_path.replace(task.dst)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def main() -> int:
    args = parse_args()

    try:
        validate_args(args)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    input_path = args.input_path.expanduser().resolve()
    output_path = args.output_path.expanduser().resolve(strict=False)

    if not input_path.exists():
        print(f"Input path not found: {input_path}", file=sys.stderr)
        return 2

    try:
        backend = choose_backend(args.backend)
        tasks = build_tasks(input_path, output_path, collect_extensions(args.extra_extension), args.limit)
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if not tasks:
        print(f"No supported image files found under: {input_path}")
        return 0

    converted = 0
    planned = 0
    skipped = 0
    failed = 0

    print(f"Planned {len(tasks)} file(s). Backend: {backend}. DPI: {args.dpi}. Quality: {args.quality}")
    for task in tasks:
        if task.dst.exists() and not args.overwrite:
            skipped += 1
            print(f"[skip] {task.dst} (already exists)")
            continue

        task.dst.parent.mkdir(parents=True, exist_ok=True)

        if args.dry_run:
            print(f"[dry-run] {task.src} -> {task.dst}")
            planned += 1
            continue

        try:
            convert_image(task, backend, args.dpi, args.quality)
            converted += 1
            print(f"[ok] {task.src} -> {task.dst}")
        except RuntimeError as exc:
            failed += 1
            print(f"[error] {task.src}: {exc}", file=sys.stderr)

    if args.dry_run:
        print(f"Done. planned={planned}, skipped={skipped}, failed={failed}")
    else:
        print(f"Done. converted={converted}, skipped={skipped}, failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
