from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "mineru_fulltext_extract.py"
SPEC = importlib.util.spec_from_file_location("mineru_fulltext_extract", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


class FulltextNormalizationTests(unittest.TestCase):
    def request_text(self, payload: dict[str, object]) -> str:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.pdf"
            source.write_bytes(b"fixture")
            with mock.patch.object(MODULE.request, "urlopen", return_value=FakeResponse(payload)):
                return MODULE.request_fulltext(
                    api_url="https://unstructure.example/mineru_with_images",
                    file_path=source,
                    token="test-token",
                    provider=None,
                    model=None,
                    timeout=1,
                    insecure=False,
                )

    def test_direct_txt_normalizes_escaped_underscores_only(self) -> None:
        actual = self.request_text(
            {"txt": r"UNSTRUCTURE\_CANARY\_42 keeps C:\notes and \*literal\*"}
        )

        self.assertEqual(actual, r"UNSTRUCTURE_CANARY_42 keeps C:\notes and \*literal\*")

    def test_result_chunks_normalize_escaped_underscores(self) -> None:
        actual = self.request_text(
            {
                "result": [
                    {"text": r"first\_field"},
                    {"text": "second_field"},
                    {"metadata": "ignored"},
                ]
            }
        )

        self.assertEqual(actual, "first_field\n\nsecond_field")


if __name__ == "__main__":
    unittest.main()
