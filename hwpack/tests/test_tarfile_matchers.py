from StringIO import StringIO
import tarfile

from testtools import TestCase

from hwpack.tarfile_matchers import (
    TarfileHasFile,
    TarfileMissingPathMismatch,
    TarfileWrongValueMismatch,
    )
from hwpack.testing import test_tarfile


class TarfileMissingPathMismatchTests(TestCase):

    def test_describe(self):
        mismatch = TarfileMissingPathMismatch("foo", "bar")
        self.assertEqual('"foo" has no path "bar"', mismatch.describe())

    def test_eq(self):
        mismatch1 = TarfileMissingPathMismatch("foo", "bar")
        mismatch2 = TarfileMissingPathMismatch("foo", "bar")
        self.assertEqual(mismatch1, mismatch2)

    def test_no_eq_different_tarball(self):
        mismatch1 = TarfileMissingPathMismatch("foo", "bar")
        mismatch2 = TarfileMissingPathMismatch("baz", "bar")
        self.assertNotEqual(mismatch1, mismatch2)

    def test_no_eq_different_path(self):
        mismatch1 = TarfileMissingPathMismatch("foo", "bar")
        mismatch2 = TarfileMissingPathMismatch("foo", "baz")
        self.assertNotEqual(mismatch1, mismatch2)

    def test_hash_equal(self):
        mismatch1 = TarfileMissingPathMismatch("foo", "bar")
        mismatch2 = TarfileMissingPathMismatch("foo", "bar")
        self.assertEqual(hash(mismatch1), hash(mismatch2))

    def test_different_tarball_different_hash(self):
        mismatch1 = TarfileMissingPathMismatch("foo", "bar")
        mismatch2 = TarfileMissingPathMismatch("baz", "bar")
        self.assertNotEqual(hash(mismatch1), hash(mismatch2))

    def test_different_path_different_hash(self):
        mismatch1 = TarfileMissingPathMismatch("foo", "bar")
        mismatch2 = TarfileMissingPathMismatch("foo", "baz")
        self.assertNotEqual(hash(mismatch1), hash(mismatch2))


class TarfileWrongTypeMismatchTests(TestCase):

    def test_describe(self):
        mismatch = TarfileWrongValueMismatch("type", "foo", "bar", 1, 2)
        self.assertEqual(
            'The path "bar" in "foo" has type 2, expected 1',
            mismatch.describe())

    def test_eq(self):
        mismatch1 = TarfileWrongValueMismatch("type", "foo", "bar", 1, 2)
        mismatch2 = TarfileWrongValueMismatch("type", "foo", "bar", 1, 2)
        self.assertEqual(mismatch1, mismatch2)

    def test_not_eq_different_attribute(self):
        mismatch1 = TarfileWrongValueMismatch("type", "foo", "bar", 1, 2)
        mismatch2 = TarfileWrongValueMismatch("size", "foo", "bar", 1, 2)
        self.assertNotEqual(mismatch1, mismatch2)

    def test_not_eq_different_tarball(self):
        mismatch1 = TarfileWrongValueMismatch("type", "foo", "bar", 1, 2)
        mismatch2 = TarfileWrongValueMismatch("type", "baz", "bar", 1, 2)
        self.assertNotEqual(mismatch1, mismatch2)

    def test_not_eq_different_path(self):
        mismatch1 = TarfileWrongValueMismatch("type", "foo", "bar", 1, 2)
        mismatch2 = TarfileWrongValueMismatch("type", "foo", "baz", 1, 2)
        self.assertNotEqual(mismatch1, mismatch2)

    def test_not_eq_different_expected(self):
        mismatch1 = TarfileWrongValueMismatch("type", "foo", "bar", 1, 2)
        mismatch2 = TarfileWrongValueMismatch("type", "foo", "bar", 3, 2)
        self.assertNotEqual(mismatch1, mismatch2)

    def test_not_eq_different_actual(self):
        mismatch1 = TarfileWrongValueMismatch("type", "foo", "bar", 1, 2)
        mismatch2 = TarfileWrongValueMismatch("type", "foo", "bar", 1, 3)
        self.assertNotEqual(mismatch1, mismatch2)

    def test_hash_equal(self):
        mismatch1 = TarfileWrongValueMismatch("type", "foo", "bar", 1, 2)
        mismatch2 = TarfileWrongValueMismatch("type", "foo", "bar", 1, 2)
        self.assertEqual(hash(mismatch1), hash(mismatch2))

    def test_different_attribute_different_hash(self):
        mismatch1 = TarfileWrongValueMismatch("type", "foo", "bar", 1, 2)
        mismatch2 = TarfileWrongValueMismatch("size", "foo", "bar", 1, 2)
        self.assertNotEqual(hash(mismatch1), hash(mismatch2))

    def test_different_tarball_different_hash(self):
        mismatch1 = TarfileWrongValueMismatch("type", "foo", "bar", 1, 2)
        mismatch2 = TarfileWrongValueMismatch("type", "baz", "bar", 1, 2)
        self.assertNotEqual(hash(mismatch1), hash(mismatch2))

    def test_different_path_different_hash(self):
        mismatch1 = TarfileWrongValueMismatch("type", "foo", "bar", 1, 2)
        mismatch2 = TarfileWrongValueMismatch("type", "foo", "baz", 1, 2)
        self.assertNotEqual(hash(mismatch1), hash(mismatch2))

    def test_different_expected_different_hash(self):
        mismatch1 = TarfileWrongValueMismatch("type", "foo", "bar", 1, 2)
        mismatch2 = TarfileWrongValueMismatch("type", "foo", "bar", 3, 2)
        self.assertNotEqual(hash(mismatch1), hash(mismatch2))

    def test_different_actual_different_hash(self):
        mismatch1 = TarfileWrongValueMismatch("type", "foo", "bar", 1, 2)
        mismatch2 = TarfileWrongValueMismatch("type", "foo", "bar", 1, 3)
        self.assertNotEqual(hash(mismatch1), hash(mismatch2))


class TarfileHasFileTests(TestCase):

    def test_str(self):
        matcher = TarfileHasFile("foo")
        self.assertEqual('tarfile has file "foo"', str(matcher))

    def test_matches(self):
        backing_file = StringIO()
        with test_tarfile(contents=[("foo", "")]) as tf:
            matcher = TarfileHasFile("foo")
            self.assertIs(None, matcher.match(tf))

    def test_mismatches_missing_path(self):
        backing_file = StringIO()
        with test_tarfile() as tf:
            matcher = TarfileHasFile("foo")
            mismatch = matcher.match(tf)
            self.assertIsInstance(mismatch, TarfileMissingPathMismatch)
            self.assertEqual(TarfileMissingPathMismatch(tf, "foo"), mismatch)

    def assertValueMismatch(self, mismatch, tarball, path, attribute,
                            expected, actual):
        self.assertIsInstance(mismatch, TarfileWrongValueMismatch)
        expected_mismatch = TarfileWrongValueMismatch(
            attribute, tarball, path, expected, actual)
        self.assertEqual(expected_mismatch, mismatch)

    def test_mismatches_wrong_type(self):
        backing_file = StringIO()
        with test_tarfile(contents=[("foo", "")]) as tf:
            matcher = TarfileHasFile("foo", type=tarfile.DIRTYPE)
            mismatch = matcher.match(tf)
            self.assertValueMismatch(
                mismatch, tf, "foo", "type", tarfile.DIRTYPE,
                tarfile.REGTYPE)

    def test_mismatches_wrong_size(self):
        backing_file = StringIO()
        with test_tarfile(contents=[("foo", "")]) as tf:
            matcher = TarfileHasFile("foo", size=1235)
            mismatch = matcher.match(tf)
            self.assertValueMismatch(
                mismatch, tf, "foo", "size", 1235, 0)

    def test_mismatches_wrong_mtime(self):
        backing_file = StringIO()
        with test_tarfile(contents=[("foo", "")], default_mtime=12345) as tf:
            matcher = TarfileHasFile("foo", mtime=54321)
            mismatch = matcher.match(tf)
            self.assertValueMismatch(
                mismatch, tf, "foo", "mtime", 54321, 12345)

    def test_mismatches_wrong_mode(self):
        backing_file = StringIO()
        with test_tarfile(contents=[("foo", "")]) as tf:
            matcher = TarfileHasFile("foo", mode=0000)
            mismatch = matcher.match(tf)
            self.assertValueMismatch(
                mismatch, tf, "foo", "mode", 0000, 0644)

    def test_mismatches_wrong_linkname(self):
        backing_file = StringIO()
        with test_tarfile(contents=[("foo", "")]) as tf:
            matcher = TarfileHasFile("foo", linkname="somelink")
            mismatch = matcher.match(tf)
            self.assertValueMismatch(
                mismatch, tf, "foo", "linkname", "somelink", "")

    def test_mismatches_wrong_uid(self):
        backing_file = StringIO()
        with test_tarfile(contents=[("foo", "")], default_uid=100) as tf:
            matcher = TarfileHasFile("foo", uid=99)
            mismatch = matcher.match(tf)
            self.assertValueMismatch(
                mismatch, tf, "foo", "uid", 99, 100)

    def test_mismatches_wrong_gid(self):
        backing_file = StringIO()
        with test_tarfile(contents=[("foo", "")], default_gid=100) as tf:
            matcher = TarfileHasFile("foo", gid=99)
            mismatch = matcher.match(tf)
            self.assertValueMismatch(
                mismatch, tf, "foo", "gid", 99, 100)

    def test_mismatches_wrong_uname(self):
        backing_file = StringIO()
        with test_tarfile(
            contents=[("foo", "")], default_uname="someuser") as tf:
            matcher = TarfileHasFile("foo", uname="otheruser")
            mismatch = matcher.match(tf)
            self.assertValueMismatch(
                mismatch, tf, "foo", "uname", "otheruser", "someuser")

    def test_mismatches_wrong_gname(self):
        backing_file = StringIO()
        with test_tarfile(
            contents=[("foo", "")], default_gname="somegroup") as tf:
            matcher = TarfileHasFile("foo", gname="othergroup")
            mismatch = matcher.match(tf)
            self.assertValueMismatch(
                mismatch, tf, "foo", "gname", "othergroup", "somegroup")

    def test_mismatches_wrong_content(self):
        backing_file = StringIO()
        with test_tarfile(contents=[("foo", "somecontent")]) as tf:
            matcher = TarfileHasFile("foo", content="othercontent")
            mismatch = matcher.match(tf)
            self.assertValueMismatch(
                mismatch, tf, "foo", "content", "othercontent", "somecontent")