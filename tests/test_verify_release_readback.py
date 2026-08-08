from __future__ import annotations

import unittest

from scripts.verify_release_readback import (
    resolve_exact_canonical,
    verify_release_readback,
)


NAME = "tribal_village"
VERSION = "0.1.28"
COWORLD_ID = "cow_f9094e3c-2860-4e77-9a13-eac56f754683"
MANIFEST_HASH = "sha256:example"


def coworld_list() -> list[dict[str, object]]:
    return [
        {
            "id": COWORLD_ID,
            "name": NAME,
            "version": VERSION,
            "canonical": True,
            "manifest_hash": MANIFEST_HASH,
        }
    ]


def coworld_status() -> dict[str, object]:
    return {
        "coworld": {
            "id": COWORLD_ID,
            "name": NAME,
            "version": VERSION,
            "canonical": True,
            "manifest_hash": MANIFEST_HASH,
        },
        "hosted_smoke_episodes": [
            {"id": "ereq_example", "status": "completed", "error": None}
        ],
        "certification": {
            "coworld_id": COWORLD_ID,
            "state": "certified",
            "certified": True,
            "contract_version": "coworld-v1",
            "transcript_summary": [{"id": "matriculate", "status": "pass"}],
        },
    }


class ReleaseReadbackTest(unittest.TestCase):
    def test_accepts_exact_canonical_certified_release(self) -> None:
        message = verify_release_readback(
            coworld_list(), coworld_status(), name=NAME, version=VERSION
        )
        self.assertIn("is canonical and certified", message)

    def test_accepts_status_without_list_only_fields(self) -> None:
        status = coworld_status()
        coworld = status["coworld"]
        assert isinstance(coworld, dict)
        del coworld["canonical"]
        del coworld["manifest_hash"]
        verify_release_readback(coworld_list(), status, name=NAME, version=VERSION)

    def test_rejects_noncanonical_release(self) -> None:
        rows = coworld_list()
        rows[0]["canonical"] = False
        with self.assertRaisesRegex(ValueError, "is not canonical"):
            resolve_exact_canonical(rows, name=NAME, version=VERSION)

    def test_rejects_pending_certification(self) -> None:
        status = coworld_status()
        certification = status["certification"]
        assert isinstance(certification, dict)
        certification["state"] = "certifying"
        certification["certified"] = False
        with self.assertRaisesRegex(ValueError, "did not finish certified"):
            verify_release_readback(coworld_list(), status, name=NAME, version=VERSION)

    def test_rejects_failed_hosted_smoke(self) -> None:
        status = coworld_status()
        episodes = status["hosted_smoke_episodes"]
        assert isinstance(episodes, list)
        episodes[0]["status"] = "failed"
        with self.assertRaisesRegex(ValueError, "hosted smoke is not clean"):
            verify_release_readback(coworld_list(), status, name=NAME, version=VERSION)


if __name__ == "__main__":
    unittest.main()
