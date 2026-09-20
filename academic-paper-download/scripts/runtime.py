#!/usr/bin/env python3
"""Manage and run the skill's hash-locked, external Python environment."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "academic-paper-download.runtime.v1"
MINIMUM_PYTHON = (3, 10)
SKILL_ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = SKILL_ROOT / "requirements.lock"
SMOKE_SCRIPT = SKILL_ROOT / "scripts" / "smoke_test.py"
ENTRYPOINTS = {
    "fetch": SKILL_ROOT / "scripts" / "fetch.py",
    "browser-finalize": SKILL_ROOT / "scripts" / "finalize_browser_download.py",
    "notify-human": SKILL_ROOT / "scripts" / "notify_human.py",
}


class RuntimeFailure(Exception):
    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details

    def payload(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, **self.details}


def _emit(payload: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if payload.get("ok"):
        print((payload.get("data") or {}).get("message", "ok"))
        return
    error = payload.get("error") or {}
    print(
        f"{error.get('code', 'runtime_error')}: {error.get('message', 'unknown error')}"
    )


def _check_host_python() -> None:
    if sys.version_info < MINIMUM_PYTHON:
        raise RuntimeFailure(
            "python_incompatible",
            "Academic Paper Download requires Python 3.10 or newer",
            python=sys.version.split()[0],
            executable=sys.executable,
        )


def _lock_digest() -> str:
    try:
        content = LOCK_PATH.read_bytes()
    except OSError as exc:
        raise RuntimeFailure(
            "lock_missing",
            f"Could not read the runtime lock: {exc}",
            lock=str(LOCK_PATH),
        ) from exc
    return hashlib.sha256(content).hexdigest()


def _locked_pypdf_version() -> str:
    try:
        content = LOCK_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeFailure(
            "lock_missing",
            f"Could not read the runtime lock: {exc}",
            lock=str(LOCK_PATH),
        ) from exc
    match = re.search(r"(?m)^pypdf==([0-9]+(?:\.[0-9]+){2})\s+\\$", content)
    if not match:
        raise RuntimeFailure(
            "lock_invalid",
            "requirements.lock must contain one exact pypdf version",
            lock=str(LOCK_PATH),
        )
    return match.group(1)


def _cache_base() -> Path:
    explicit = os.environ.get("ACADEMIC_PAPER_DOWNLOAD_CACHE_DIR", "").strip()
    if explicit:
        return Path(explicit).expanduser().absolute()
    xdg = os.environ.get("XDG_CACHE_HOME", "").strip()
    if xdg:
        root = Path(xdg).expanduser()
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Caches"
    elif os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        root = Path(os.environ["LOCALAPPDATA"])
    else:
        root = Path.home() / ".cache"
    return root / "tiangong-skills" / "academic-paper-download"


def _runtime_id() -> str:
    implementation = getattr(sys.implementation, "name", "python")
    python_tag = f"{implementation}-{sys.version_info.major}.{sys.version_info.minor}"
    platform_tag = f"{sys.platform}-{platform.machine() or 'unknown'}"
    safe_platform = re.sub(r"[^a-zA-Z0-9_.-]+", "-", platform_tag)
    return f"{_lock_digest()[:16]}-{python_tag}-{safe_platform}"


def _runtime_dir() -> Path:
    return _cache_base() / _runtime_id()


def _runtime_python(directory: Path | None = None) -> Path:
    root = directory or _runtime_dir()
    return root / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _marker_path(directory: Path | None = None) -> Path:
    return (directory or _runtime_dir()) / "runtime.json"


def _read_marker(directory: Path | None = None) -> dict[str, Any] | None:
    try:
        payload = json.loads(_marker_path(directory).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _environment_ready(directory: Path | None = None) -> bool:
    marker = _read_marker(directory)
    return bool(
        _runtime_python(directory).is_file()
        and marker
        and marker.get("schema_version") == SCHEMA_VERSION
        and marker.get("lock_sha256") == _lock_digest()
        and marker.get("pypdf") == _locked_pypdf_version()
    )


def _verify_environment() -> Path:
    directory = _runtime_dir()
    python = _runtime_python(directory)
    if not _environment_ready(directory):
        raise RuntimeFailure(
            "runtime_missing",
            "The locked runtime is not installed; run runtime.py bootstrap --locked explicitly",
            runtime_dir=str(directory),
        )
    expected = _locked_pypdf_version()
    check = subprocess.run(
        [
            str(python),
            "-c",
            (
                "import importlib.metadata as m, pypdf; "
                f"assert m.version('pypdf') == {expected!r}; "
                "assert hasattr(pypdf, 'PdfReader')"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    if check.returncode != 0:
        raise RuntimeFailure(
            "runtime_invalid",
            "The locked runtime failed its dependency preflight",
            runtime_dir=str(directory),
            detail=check.stderr.strip()[-1000:],
        )
    return python


def _write_marker(directory: Path) -> None:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "lock_sha256": _lock_digest(),
        "pypdf": _locked_pypdf_version(),
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
    }
    _marker_path(directory).write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )


def bootstrap(*, as_json: bool) -> int:
    _check_host_python()
    destination = _runtime_dir()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if _environment_ready(destination):
        python = _verify_environment()
        _emit(
            {
                "ok": True,
                "data": {
                    "message": "Locked runtime already ready",
                    "runtime_dir": str(destination),
                    "python": str(python),
                    "pypdf": _locked_pypdf_version(),
                    "skipped": True,
                },
            },
            as_json=as_json,
        )
        return 0
    if destination.exists():
        raise RuntimeFailure(
            "runtime_invalid",
            "A runtime directory exists but does not match the current lock",
            runtime_dir=str(destination),
        )

    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
    )
    try:
        venv.EnvBuilder(with_pip=True, clear=False, symlinks=os.name != "nt").create(
            temporary
        )
        python = _runtime_python(temporary)
        install = subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--no-input",
                "--no-compile",
                "--require-hashes",
                "-r",
                str(LOCK_PATH),
            ],
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        if install.returncode != 0:
            raise RuntimeFailure(
                "dependency_install_failed",
                "Could not install the hash-locked runtime",
                detail=install.stderr.strip()[-2000:],
            )
        _write_marker(temporary)
        try:
            os.replace(temporary, destination)
        except OSError:
            if not _environment_ready(destination):
                raise
        python = _verify_environment()
    finally:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)

    _emit(
        {
            "ok": True,
            "data": {
                "message": "Installed hash-locked runtime",
                "runtime_dir": str(destination),
                "python": str(python),
                "pypdf": _locked_pypdf_version(),
                "skipped": False,
            },
        },
        as_json=as_json,
    )
    return 0


def doctor(*, as_json: bool) -> int:
    _check_host_python()
    python = _verify_environment()
    _emit(
        {
            "ok": True,
            "data": {
                "message": "Locked runtime preflight passed",
                "runtime_dir": str(_runtime_dir()),
                "python": str(python),
                "pypdf": _locked_pypdf_version(),
                "lock_sha256": _lock_digest(),
            },
        },
        as_json=as_json,
    )
    return 0


def smoke(*, as_json: bool) -> int:
    python = _verify_environment()
    environment = {
        **os.environ,
        "ACADEMIC_PAPER_DOWNLOAD_OFFLINE": "1",
        "ACADEMIC_PAPER_DOWNLOAD_EXPECTED_PYPDF": _locked_pypdf_version(),
        "PIP_NO_INDEX": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    completed = subprocess.run(
        [str(python), str(SMOKE_SCRIPT), *(["--json"] if as_json else [])],
        check=False,
        env=environment,
    )
    return completed.returncode


def run_entrypoint(command: str, arguments: list[str]) -> int:
    python = _verify_environment()
    script = ENTRYPOINTS[command]
    completed = subprocess.run(
        [str(python), str(script), *arguments],
        check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    return completed.returncode


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    bootstrap_parser = subparsers.add_parser(
        "bootstrap", help="Explicitly install the exact locked runtime"
    )
    bootstrap_parser.add_argument("--locked", action="store_true", required=True)
    bootstrap_parser.add_argument("--json", action="store_true")
    doctor_parser = subparsers.add_parser(
        "doctor", help="Check the installed runtime without changing it"
    )
    doctor_parser.add_argument("--json", action="store_true")
    smoke_parser = subparsers.add_parser(
        "smoke", help="Run the network-free PDF validation smoke test"
    )
    smoke_parser.add_argument("--offline", action="store_true", required=True)
    smoke_parser.add_argument("--json", action="store_true")
    for command in ENTRYPOINTS:
        command_parser = subparsers.add_parser(command, add_help=False)
        command_parser.add_argument("arguments", nargs=argparse.REMAINDER)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    as_json = False
    try:
        if arguments and arguments[0] in ENTRYPOINTS:
            return run_entrypoint(arguments[0], arguments[1:])
        args = _parser().parse_args(arguments)
        as_json = bool(getattr(args, "json", False))
        if args.command == "bootstrap":
            return bootstrap(as_json=as_json)
        if args.command == "doctor":
            return doctor(as_json=as_json)
        if args.command == "smoke":
            return smoke(as_json=as_json)
        raise RuntimeFailure("runtime_command_invalid", "Unknown runtime command")
    except RuntimeFailure as exc:
        _emit({"ok": False, "error": exc.payload()}, as_json=as_json)
        return 4 if exc.code == "dependency_install_failed" else 3
    except OSError as exc:
        failure = RuntimeFailure("runtime_io_error", str(exc))
        _emit({"ok": False, "error": failure.payload()}, as_json=as_json)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
