from __future__ import annotations

import unittest

from scripts.pin_manifest_refs import pin


class ReleaseManifestTest(unittest.TestCase):
    def test_pins_root_and_nested_main_source_urls(self) -> None:
        sha = "a" * 40
        root = "https://github.com/Metta-AI/coworld-tribal-village/tree/main"
        nested = root + "/players/villager"

        self.assertEqual(
            pin({"root": root, "nested": nested}, sha),
            {
                "root": root.replace("/main", f"/{sha}"),
                "nested": nested.replace("/main/", f"/{sha}/"),
            },
        )


if __name__ == "__main__":
    unittest.main()
