"""Exercise the version gate that runs before publishing distributions."""

import unittest

from tools.check_release import validate_release


class ReleaseTests(unittest.TestCase):
    def test_supported_semver_tags_match_python_versions(self):
        for tag, version, prerelease in [
            ("v0.1.0", "0.1.0", False),
            ("v1.2.3", "1.2.3", False),
            ("v10.20.30", "10.20.30", False),
            ("v1.2.3-alpha.0", "1.2.3a0", True),
            ("v1.2.3-beta.2", "1.2.3b2", True),
            ("v1.2.3-rc.12", "1.2.3rc12", True),
        ]:
            with self.subTest(tag=tag):
                validate_release(tag, version, prerelease)

    def test_noncanonical_or_unsupported_tags_are_rejected(self):
        for tag in [
            "1.2.3",
            "v1.2",
            "v01.2.3",
            "v1.02.3",
            "v1.2.03",
            "v1.2.3-rc.01",
            "v1.2.3-rc",
            "v1.2.3-preview.1",
            "v1.2.3+build.1",
            "v1.2.3.post1",
            "v1.2.3\n",
            "v١.2.3",
        ]:
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                validate_release(tag, "1.2.3", False)

    def test_tag_version_and_release_kind_must_agree(self):
        for tag, version, prerelease in [
            ("v1.2.3", "1.2.4", False),
            ("v1.2.3", "1.2.3", True),
            ("v1.2.3-rc.1", "1.2.3rc2", True),
            ("v1.2.3-rc.1", "1.2.3", True),
            ("v1.2.3-rc.1", "1.2.3rc1", False),
        ]:
            with self.subTest(tag=tag, version=version), self.assertRaises(ValueError):
                validate_release(tag, version, prerelease)
