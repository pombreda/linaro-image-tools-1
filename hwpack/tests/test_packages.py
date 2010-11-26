import os
from StringIO import StringIO
import subprocess
import textwrap

from debian.debfile import DebFile
from testtools import TestCase

from hwpack.packages import (
    DependencyNotSatisfied,
    FetchedPackage,
    get_packages_file,
    IsolatedAptCache,
    PackageFetcher,
    PackageMaker,
    stringify_relationship,
    )
from hwpack.testing import (
    AptSourceFixture,
    ContextManagerFixture,
    DummyFetchedPackage,
    TestCaseWithFixtures,
    )


class GetPackagesFileTests(TestCase):

    def test_single_stanza(self):
        package = DummyFetchedPackage("foo", "1.1", architecture="armel")
        self.assertEqual(textwrap.dedent("""\
            Package: foo
            Version: 1.1
            Filename: %(filename)s
            Size: %(size)d
            Architecture: armel
            MD5sum: %(md5)s
            \n""" % {
                'filename': package.filename,
                'size': package.size,
                'md5': package.md5,
            }), get_packages_file([package]))

    def test_two_stanzas(self):
        package1 = DummyFetchedPackage("foo", "1.1")
        package2 = DummyFetchedPackage("bar", "1.2")
        self.assertEqual(
            get_packages_file([package1]) + get_packages_file([package2]),
            get_packages_file([package1, package2]))

    def get_stanza(self, package, relationships=""):
        stanza = textwrap.dedent("""\
            Package: foo
            Version: 1.1
            Filename: %(filename)s
            Size: %(size)d
            Architecture: all
            """ % {
            'filename': package.filename,
            'size': package.size,
            })
        stanza += relationships
        stanza += "MD5sum: %s\n\n" % package.md5
        return stanza

    def test_with_depends(self):
        package = DummyFetchedPackage("foo", "1.1", depends="bar | baz")
        self.assertEqual(
            self.get_stanza(package, "Depends: bar | baz\n"),
            get_packages_file([package]))

    def test_with_pre_depends(self):
        package = DummyFetchedPackage("foo", "1.1", pre_depends="bar | baz")
        self.assertEqual(
            self.get_stanza(package, "Pre-Depends: bar | baz\n"),
            get_packages_file([package]))

    def test_with_conflicts(self):
        package = DummyFetchedPackage("foo", "1.1", conflicts="bar | baz")
        self.assertEqual(
            self.get_stanza(package, "Conflicts: bar | baz\n"),
            get_packages_file([package]))

    def test_with_recommends(self):
        package = DummyFetchedPackage("foo", "1.1", recommends="bar | baz")
        self.assertEqual(
            self.get_stanza(package, "Recommends: bar | baz\n"),
            get_packages_file([package]))

    def test_with_provides(self):
        package = DummyFetchedPackage("foo", "1.1", provides="bar")
        self.assertEqual(
            self.get_stanza(package, "Provides: bar\n"),
            get_packages_file([package]))

    def test_with_replaces(self):
        package = DummyFetchedPackage("foo", "1.1", replaces="bar (<< 2.0)")
        self.assertEqual(
            self.get_stanza(package, "Replaces: bar (<< 2.0)\n"),
            get_packages_file([package]))

    def test_with_breaks(self):
        package = DummyFetchedPackage("foo", "1.1", breaks="bar (<< 2.0)")
        self.assertEqual(
            self.get_stanza(package, "Breaks: bar (<< 2.0)\n"),
            get_packages_file([package]))

    def test_with_extra_text(self):
        package = DummyFetchedPackage("foo", "1.1")
        self.assertEqual(textwrap.dedent("""\
            Package: foo
            Status: bar
            Version: 1.1
            Filename: %(filename)s
            Size: %(size)d
            Architecture: all
            MD5sum: %(md5)s
            \n""" % {
                'filename': package.filename,
                'size': package.size,
                'md5': package.md5,
            }), get_packages_file([package], extra_text="Status: bar"))


class StringifyRelationshipTests(TestCaseWithFixtures):

    def test_no_relationship(self):
        target_package = DummyFetchedPackage("foo", "1.0")
        source = self.useFixture(AptSourceFixture([target_package]))
        with IsolatedAptCache([source.sources_entry]) as cache:
            candidate = cache.cache['foo'].candidate
            self.assertEqual(
                None, stringify_relationship(candidate, "Depends"))

    def test_single_package(self):
        target_package = DummyFetchedPackage("foo", "1.0", depends="bar")
        source = self.useFixture(AptSourceFixture([target_package]))
        with IsolatedAptCache([source.sources_entry]) as cache:
            candidate = cache.cache['foo'].candidate
            self.assertEqual(
                "bar", stringify_relationship(candidate, "Depends"))

    def test_multiple_package(self):
        target_package = DummyFetchedPackage("foo", "1.0", depends="bar, baz")
        source = self.useFixture(AptSourceFixture([target_package]))
        with IsolatedAptCache([source.sources_entry]) as cache:
            candidate = cache.cache['foo'].candidate
            self.assertEqual(
                "bar, baz", stringify_relationship(candidate, "Depends"))

    def test_alternative_packages(self):
        target_package = DummyFetchedPackage(
            "foo", "1.0", depends="bar | baz")
        source = self.useFixture(AptSourceFixture([target_package]))
        with IsolatedAptCache([source.sources_entry]) as cache:
            candidate = cache.cache['foo'].candidate
            self.assertEqual(
                "bar | baz", stringify_relationship(candidate, "Depends"))

    def test_package_with_version(self):
        target_package = DummyFetchedPackage(
            "foo", "1.0", depends="baz (<= 2.0)")
        source = self.useFixture(AptSourceFixture([target_package]))
        with IsolatedAptCache([source.sources_entry]) as cache:
            candidate = cache.cache['foo'].candidate
            self.assertEqual(
                "baz (<= 2.0)", stringify_relationship(candidate, "Depends"))


class PackageMakerTests(TestCaseWithFixtures):

    def test_enter_twice_fails(self):
        maker = PackageMaker()
        maker.__enter__()
        self.assertRaises(AssertionError, maker.__enter__)

    def test_exit_without_enter_silent(self):
        maker = PackageMaker()
        maker.__exit__()

    def test_make_temporary_directory_without_enter_fails(self):
        maker = PackageMaker()
        self.assertRaises(AssertionError, maker.make_temporary_directory)

    def test_make_temporary_directory_makes_directory(self):
        maker = PackageMaker()
        self.useFixture(ContextManagerFixture(maker))
        tmpdir = maker.make_temporary_directory()
        self.assertTrue(os.path.isdir(tmpdir))

    def test_exit_removes_temporary_directory(self):
        maker = PackageMaker()
        self.useFixture(ContextManagerFixture(maker))
        tmpdir = maker.make_temporary_directory()
        maker.__exit__()
        self.assertFalse(os.path.isdir(tmpdir))

    def test_make_package_creates_file(self):
        maker = PackageMaker()
        self.useFixture(ContextManagerFixture(maker))
        deb_path = maker.make_package('foo', '1.0', {})
        self.assertTrue(os.path.exists(deb_path))

    def test_make_package_creates_deb_with_given_package_name(self):
        maker = PackageMaker()
        self.useFixture(ContextManagerFixture(maker))
        deb_path = maker.make_package('foo', '1.0', {})
        deb_pkg = DebFile(deb_path)
        self.assertEqual('foo', deb_pkg.control.debcontrol()['Package'])

    def test_make_package_creates_deb_with_correct_file_name(self):
        maker = PackageMaker()
        self.useFixture(ContextManagerFixture(maker))
        deb_path = maker.make_package('foo', '1.0', {})
        proc = subprocess.Popen(
            ['dpkg-name', deb_path], stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT)
        output = proc.communicate()[0]
        self.assertTrue(
            'skipping' in output,
            "'skipping' was not found in dpkg-name output:\n%s" % output)

    def test_make_package_creates_deb_with_given_version(self):
        maker = PackageMaker()
        self.useFixture(ContextManagerFixture(maker))
        deb_path = maker.make_package('foo', '1.0ubuntu1', {})
        deb_pkg = DebFile(deb_path)
        self.assertEqual(
            '1.0ubuntu1', deb_pkg.control.debcontrol()['Version'])

    def assertControlFieldsPreserved(self, fields):
        maker = PackageMaker()
        self.useFixture(ContextManagerFixture(maker))
        deb_path = maker.make_package(
            'foo', '1.0', fields)
        deb_pkg = DebFile(deb_path)
        for key, value in fields.items():
            self.assertEqual(
                value, deb_pkg.control.debcontrol()[key])

    def test_make_package_creates_deb_with_given_depends(self):
        self.assertControlFieldsPreserved({'Depends': 'bar, baz (>= 1.0)'})

    def test_make_package_creates_deb_with_given_predepends(self):
        self.assertControlFieldsPreserved({'Pre-Depends': 'bar, baz (>= 1.0)'})

    def test_make_package_creates_deb_with_given_conflicts(self):
        self.assertControlFieldsPreserved({'Conflicts': 'bar, baz (>= 1.0)'})

    def test_make_package_creates_deb_with_given_recommends(self):
        self.assertControlFieldsPreserved({'Recommends': 'bar, baz (>= 1.0)'})

    def test_make_package_creates_deb_with_given_provides(self):
        self.assertControlFieldsPreserved({'Provides': 'bar, baz (= 1.0)'})

    def test_make_package_creates_deb_with_given_replaces(self):
        self.assertControlFieldsPreserved({'Replaces': 'bar, baz (>= 1.0)'})

    def test_make_package_creates_deb_with_given_breaks(self):
        self.assertControlFieldsPreserved({'Breaks': 'bar, baz (>= 1.0)'})

    def test_make_package_creates_deb_with_all_given_fields(self):
        self.assertControlFieldsPreserved({
            'Depends': 'bar, baz (>= 1.0)',
            'Pre-Depends': 'bar, baz (>= 1.0)',
            'Conflicts': 'bar, baz (>= 1.0)',
            'Recommends': 'bar, baz (>= 1.0)',
            'Provides': 'bar, baz (= 1.0)',
            'Replaces': 'bar, baz (>= 1.0)',
            'Breaks': 'bar, baz (>= 1.0)',
            })

    def test_unknown_field_name_fails(self):
        maker = PackageMaker()
        self.useFixture(ContextManagerFixture(maker))
        self.assertRaises(
            ValueError, maker.make_package,
            'foo', '1.0', {'InvalidField': 'value'})

    def test_arch_all_by_default(self):
        maker = PackageMaker()
        self.useFixture(ContextManagerFixture(maker))
        deb_path = maker.make_package('foo', '1.0', {})
        deb_pkg = DebFile(deb_path)
        self.assertEqual("all", deb_pkg.control.debcontrol()['Architecture'])
        


class FetchedPackageTests(TestCaseWithFixtures):

    def test_attributes(self):
        package = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa",
            "armel")
        self.assertEqual("foo", package.name)
        self.assertEqual("1.1", package.version)
        self.assertEqual("foo_1.1.deb", package.filename)
        self.assertEqual(None, package.content)
        self.assertEqual(4, package.size)
        self.assertEqual("aaaa", package.md5)
        self.assertEqual("armel", package.architecture)

    def test_equal(self):
        package1 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel")
        package2 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel")
        self.assertEqual(package1, package2)
        self.assertFalse(package1 != package2)

    def test_not_equal_different_name(self):
        package1 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel")
        package2 = FetchedPackage(
            "bar", "1.1", "foo_1.1.deb", 4, "aaaa", "armel")
        self.assertNotEqual(package1, package2)

    def test_not_equal_different_version(self):
        package1 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel")
        package2 = FetchedPackage(
            "foo", "1.2", "foo_1.1.deb", 4, "aaaa", "armel")
        self.assertNotEqual(package1, package2)

    def test_not_equal_different_filename(self):
        package1 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel")
        package2 = FetchedPackage(
            "foo", "1.1", "afoo_1.1.deb", 4, "aaaa", "armel")
        self.assertNotEqual(package1, package2)

    def test_not_equal_different_size(self):
        package1 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel")
        package2 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 5, "aaaa", "armel")
        self.assertNotEqual(package1, package2)

    def test_not_equal_different_md5(self):
        package1 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel")
        package2 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "bbbb", "armel")
        self.assertNotEqual(package1, package2)

    def test_not_equal_different_architecture(self):
        package1 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel")
        package2 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "i386")
        self.assertNotEqual(package1, package2)

    def test_not_equal_different_depends(self):
        package1 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel", depends="bar")
        package2 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel", depends="baz")
        self.assertNotEqual(package1, package2)

    def test_not_equal_different_depends_one_None(self):
        package1 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel", depends="bar")
        package2 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel", depends=None)
        self.assertNotEqual(package1, package2)

    def test_equal_same_depends(self):
        package1 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel", depends="bar")
        package2 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel", depends="bar")
        self.assertEqual(package1, package2)

    def test_not_equal_different_pre_depends(self):
        package1 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel",
            pre_depends="bar")
        package2 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel",
            pre_depends="baz")
        self.assertNotEqual(package1, package2)

    def test_not_equal_different_pre_depends_one_None(self):
        package1 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel",
            pre_depends="bar")
        package2 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel",
            pre_depends=None)
        self.assertNotEqual(package1, package2)

    def test_equal_same_pre_depends(self):
        package1 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel",
            pre_depends="bar")
        package2 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel",
            pre_depends="bar")
        self.assertEqual(package1, package2)

    def test_not_equal_different_conflicts(self):
        package1 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel", conflicts="bar")
        package2 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel", conflicts="baz")
        self.assertNotEqual(package1, package2)

    def test_not_equal_different_conflicts_one_None(self):
        package1 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel",
            conflicts="bar")
        package2 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel",
            conflicts=None)
        self.assertNotEqual(package1, package2)

    def test_equal_same_conflicts(self):
        package1 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel", conflicts="bar")
        package2 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel", conflicts="bar")
        self.assertEqual(package1, package2)

    def test_not_equal_different_recommends(self):
        package1 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel",
            recommends="bar")
        package2 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel",
            recommends="baz")
        self.assertNotEqual(package1, package2)

    def test_not_equal_different_recommends_one_None(self):
        package1 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel",
            recommends="bar")
        package2 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel",
            recommends=None)
        self.assertNotEqual(package1, package2)

    def test_equal_same_recommends(self):
        package1 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel",
            recommends="bar")
        package2 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel",
            recommends="bar")
        self.assertEqual(package1, package2)

    def test_not_equal_different_provides(self):
        package1 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel",
            provides="bar")
        package2 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel",
            provides="baz")
        self.assertNotEqual(package1, package2)

    def test_not_equal_different_provides_one_None(self):
        package1 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel",
            provides="bar")
        package2 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel",
            provides=None)
        self.assertNotEqual(package1, package2)

    def test_equal_same_provides(self):
        package1 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel",
            provides="bar")
        package2 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel",
            provides="bar")
        self.assertEqual(package1, package2)

    def test_not_equal_different_replaces(self):
        package1 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel",
            replaces="bar")
        package2 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel",
            replaces="baz")
        self.assertNotEqual(package1, package2)

    def test_not_equal_different_replaces_one_None(self):
        package1 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel",
            replaces="bar")
        package2 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel",
            replaces=None)
        self.assertNotEqual(package1, package2)

    def test_equal_same_replaces(self):
        package1 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel",
            replaces="bar")
        package2 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel",
            replaces="bar")
        self.assertEqual(package1, package2)

    def test_not_equal_different_breaks(self):
        package1 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel",
            breaks="bar")
        package2 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel",
            breaks="baz")
        self.assertNotEqual(package1, package2)

    def test_not_equal_different_breaks_one_None(self):
        package1 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel",
            breaks="bar")
        package2 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel",
            breaks=None)
        self.assertNotEqual(package1, package2)

    def test_equal_same_breaks(self):
        package1 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel",
            breaks="bar")
        package2 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel",
            breaks="bar")
        self.assertEqual(package1, package2)

    def test_not_equal_different_contents(self):
        package1 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel")
        package1.content = StringIO("xxxx")
        package2 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel")
        package2.content = StringIO("yyyy")
        self.assertNotEqual(package1, package2)

    def test_not_equal_different_contents_one_unknown(self):
        package1 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel")
        package1.content = StringIO("xxxx")
        package2 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel")
        self.assertNotEqual(package1, package2)

    def test_equal_same_contents(self):
        package1 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel")
        package1.content = StringIO("xxxx")
        package2 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", 4, "aaaa", "armel")
        package2.content = StringIO("xxxx")
        self.assertEqual(package1, package2)

    def test_from_apt(self):
        target_package = DummyFetchedPackage("foo", "1.0")
        source = self.useFixture(AptSourceFixture([target_package]))
        with IsolatedAptCache([source.sources_entry]) as cache:
            candidate = cache.cache['foo'].candidate
            created_package = FetchedPackage.from_apt(
                candidate, target_package.filename,
                content=target_package.content)
            self.assertEqual(target_package, created_package)

    def assert_from_apt_translates_relationship(self, relationship):
        kwargs = {}
        kwargs[relationship] = "bar | baz (>= 1.0), zap"
        target_package = DummyFetchedPackage("foo", "1.0", **kwargs)
        source = self.useFixture(AptSourceFixture([target_package]))
        with IsolatedAptCache([source.sources_entry]) as cache:
            candidate = cache.cache['foo'].candidate
            created_package = FetchedPackage.from_apt(
                candidate, target_package.filename,
                content=target_package.content)
            self.assertEqual(target_package, created_package)

    def test_from_apt_with_depends(self):
        self.assert_from_apt_translates_relationship('depends')

    def test_from_apt_with_pre_depends(self):
        self.assert_from_apt_translates_relationship('pre_depends')

    def test_from_apt_with_conflicts(self):
        self.assert_from_apt_translates_relationship('conflicts')

    def test_from_apt_with_recommends(self):
        self.assert_from_apt_translates_relationship('recommends')

    def test_from_apt_with_replaces(self):
        self.assert_from_apt_translates_relationship('replaces')

    def test_from_apt_with_breaks(self):
        self.assert_from_apt_translates_relationship('breaks')

    def test_from_apt_with_provides(self):
        target_package = DummyFetchedPackage("foo", "1.0", provides="bar")
        source = self.useFixture(AptSourceFixture([target_package]))
        with IsolatedAptCache([source.sources_entry]) as cache:
            candidate = cache.cache['foo'].candidate
            created_package = FetchedPackage.from_apt(
                candidate, target_package.filename,
                content=target_package.content)
            self.assertEqual(target_package, created_package)

    def test_from_apt_without_content(self):
        target_package = DummyFetchedPackage("foo", "1.0")
        source = self.useFixture(AptSourceFixture([target_package]))
        with IsolatedAptCache([source.sources_entry]) as cache:
            candidate = cache.cache['foo'].candidate
            created_package = FetchedPackage.from_apt(
                candidate, target_package.filename)
            self.assertEqual(None, created_package.content)

    def test_from_deb(self):
        maker = PackageMaker()
        self.useFixture(ContextManagerFixture(maker))
        deb_file_path = maker.make_package('foo', '1.0', {})
        target_package = DummyFetchedPackage(
            "foo", "1.0", content=open(deb_file_path).read())
        created_package = FetchedPackage.from_deb(deb_file_path)
        self.assertEqual(target_package, created_package)

    def assert_from_deb_translates_relationships(self, relationships):
        maker = PackageMaker()
        self.useFixture(ContextManagerFixture(maker))
        deb_file_path = maker.make_package('foo', '1.0', relationships)
        dummy_relationships = {}
        for relationship, value in relationships.items():
            dummy_relationships[relationship.lower().replace('-', '_')] = value
        target_package = DummyFetchedPackage(
            "foo", "1.0", content=open(deb_file_path).read(), **dummy_relationships)
        created_package = FetchedPackage.from_deb(deb_file_path)
        self.assertEqual(target_package, created_package)

    def test_from_deb_with_depends(self):
        self.assert_from_deb_translates_relationships(
            {'Depends': 'bar, baz (>= 1.0)'})

    def test_from_deb_with_pre_depends(self):
        self.assert_from_deb_translates_relationships(
            {'Pre-Depends': 'bar, baz (>= 1.0)'})

    def test_from_deb_with_conflicts(self):
        self.assert_from_deb_translates_relationships(
            {'Conflicts': 'bar, baz (>= 1.0)'})

    def test_from_deb_with_recommends(self):
        self.assert_from_deb_translates_relationships(
            {'Recommends': 'bar, baz (>= 1.0)'})

    def test_from_deb_with_replaces(self):
        self.assert_from_deb_translates_relationships(
            {'Replaces': 'bar, baz (>= 1.0)'})

    def test_from_deb_with_breaks(self):
        self.assert_from_deb_translates_relationships(
            {'breaks': 'bar, baz (>= 1.0)'})


class AptCacheTests(TestCaseWithFixtures):

    def test_cleanup_removes_tempdir(self):
        cache = IsolatedAptCache([])
        cache.prepare()
        tempdir = cache.tempdir
        cache.cleanup()
        self.assertFalse(os.path.exists(tempdir))

    def test_cleanup_ignores_missing_tempdir(self):
        cache = IsolatedAptCache([])
        cache.prepare()
        cache.cleanup()
        # Check that there is no problem removing it again
        cache.cleanup()

    def test_cleanup_before_prepare(self):
        cache = IsolatedAptCache([])
        # Check that there is no problem cleaning up before we start
        cache.cleanup()

    def test_prepare_creates_tempdir(self):
        cache = IsolatedAptCache([])
        self.addCleanup(cache.cleanup)
        cache.prepare()
        self.assertTrue(os.path.isdir(cache.tempdir))

    def test_prepare_creates_var_lib_dpkg_status_file(self):
        cache = IsolatedAptCache([])
        self.addCleanup(cache.cleanup)
        cache.prepare()
        self.assertEqual(
            '',
            open(os.path.join(
                cache.tempdir, "var", "lib", "dpkg", "status")).read())

    def test_prepare_creates_var_cache_apt_archives_partial_dir(self):
        cache = IsolatedAptCache([])
        self.addCleanup(cache.cleanup)
        cache.prepare()
        self.assertTrue(
            os.path.isdir(os.path.join(
                cache.tempdir, "var", "cache", "apt", "archives",
                "partial")))

    def test_prepare_creates_var_lib_apt_lists_partial_dir(self):
        cache = IsolatedAptCache([])
        self.addCleanup(cache.cleanup)
        cache.prepare()
        self.assertTrue(
            os.path.isdir(os.path.join(
                cache.tempdir, "var", "lib", "apt", "lists", "partial")))

    def test_prepare_creates_etc_apt_sources_list_file(self):
        source1 = self.useFixture(AptSourceFixture([]))
        source2 = self.useFixture(AptSourceFixture([]))
        cache = IsolatedAptCache(
            [source1.sources_entry, source2.sources_entry])
        self.addCleanup(cache.cleanup)
        cache.prepare()
        self.assertEqual(
            "deb %s\ndeb %s\n" % (
                source1.sources_entry, source2.sources_entry),
            open(os.path.join(
                cache.tempdir, "etc", "apt", "sources.list")).read())

    def test_prepare_with_arch_creates_etc_apt_apt_conf(self):
        cache = IsolatedAptCache([], architecture="arch")
        self.addCleanup(cache.cleanup)
        cache.prepare()
        self.assertEqual(
            'Apt {\nArchitecture "arch";\nInstall-Recommends "true";\n}\n',
            open(os.path.join(
                cache.tempdir, "etc", "apt", "apt.conf")).read())

    def test_context_manager(self):
        # A smoketest that IsolatedAptCache can be used as a context
        # manager
        with IsolatedAptCache([]) as cache:
            tempdir = cache.tempdir
            self.assertTrue(os.path.isdir(tempdir))
        self.assertFalse(os.path.exists(tempdir))

    def test_set_installed_packages(self):
        cache = IsolatedAptCache([])
        self.addCleanup(cache.cleanup)
        cache.prepare()
        packages = [DummyFetchedPackage("foo", "1.0")]
        cache.set_installed_packages(packages)
        self.assertEqual(
            get_packages_file(
                packages, extra_text="Status: install ok installed"),
            open(os.path.join(
                cache.tempdir, "var", "lib", "dpkg", "status")).read())

    def test_set_installed_packages_empty_list(self):
        cache = IsolatedAptCache([])
        self.addCleanup(cache.cleanup)
        cache.prepare()
        cache.set_installed_packages([])
        self.assertEqual(
            "",
            open(os.path.join(
                cache.tempdir, "var", "lib", "dpkg", "status")).read())


class PackageFetcherTests(TestCaseWithFixtures):

    def test_context_manager(self):
        # A smoketest that PackageFetcher can be used as a context
        # manager
        with PackageFetcher([]) as fetcher:
            tempdir = fetcher.cache.tempdir
            self.assertTrue(os.path.isdir(tempdir))
        self.assertFalse(os.path.exists(tempdir))

    def get_fetcher(self, sources, architecture=None):
        fetcher = PackageFetcher(
            [s.sources_entry for s in sources], architecture=architecture)
        self.addCleanup(fetcher.cleanup)
        fetcher.prepare()
        return fetcher

    def test_fetch_packages_not_found_because_no_sources(self):
        fetcher = self.get_fetcher([])
        self.assertRaises(KeyError, fetcher.fetch_packages, ["nothere"])

    def test_fetch_packages_not_found_because_not_in_sources(self):
        available_package = DummyFetchedPackage("foo", "1.0")
        source = self.useFixture(AptSourceFixture([available_package]))
        fetcher = self.get_fetcher([source])
        self.assertRaises(KeyError, fetcher.fetch_packages, ["nothere"])

    def test_fetch_packages_not_found_one_of_two_missing(self):
        available_package = DummyFetchedPackage("foo", "1.0")
        source = self.useFixture(AptSourceFixture([available_package]))
        fetcher = self.get_fetcher([source])
        self.assertRaises(
            KeyError, fetcher.fetch_packages, ["foo", "nothere"])

    def test_fetch_packages_fetches_no_packages(self):
        available_package = DummyFetchedPackage("foo", "1.0")
        source = self.useFixture(AptSourceFixture([available_package]))
        fetcher = self.get_fetcher([source])
        self.assertEqual(0, len(fetcher.fetch_packages([])))

    def test_fetch_packages_fetches_single_package(self):
        available_package = DummyFetchedPackage("foo", "1.0")
        source = self.useFixture(AptSourceFixture([available_package]))
        fetcher = self.get_fetcher([source])
        self.assertEqual(1, len(fetcher.fetch_packages(["foo"])))

    def test_fetch_packages_fetches_correct_package(self):
        available_package = DummyFetchedPackage("foo", "1.0")
        source = self.useFixture(AptSourceFixture([available_package]))
        fetcher = self.get_fetcher([source])
        self.assertEqual(
            available_package, fetcher.fetch_packages(["foo"])[0])

    def test_fetch_packages_fetches_multiple_packages(self):
        available_packages = [
            DummyFetchedPackage("bar", "1.0"),
            DummyFetchedPackage("foo", "1.0"),
        ]
        source = self.useFixture(AptSourceFixture(available_packages))
        fetcher = self.get_fetcher([source])
        self.assertEqual(2, len(fetcher.fetch_packages(["foo", "bar"])))

    def test_fetch_packages_fetches_multiple_packages_correctly(self):
        available_packages = [
            DummyFetchedPackage("foo", "1.0"),
            DummyFetchedPackage("bar", "1.0"),
        ]
        source = self.useFixture(AptSourceFixture(available_packages))
        fetcher = self.get_fetcher([source])
        fetched = fetcher.fetch_packages(["foo", "bar"])
        self.assertEqual(available_packages[0], fetched[0])
        self.assertEqual(available_packages[1], fetched[1])

    def test_fetch_packages_fetches_newest(self):
        available_packages = [
            DummyFetchedPackage("bar", "1.0"),
            DummyFetchedPackage("bar", "1.1"),
        ]
        source = self.useFixture(AptSourceFixture(available_packages))
        fetcher = self.get_fetcher([source])
        fetched = fetcher.fetch_packages(["bar"])
        self.assertEqual(available_packages[1], fetched[0])

    def test_fetch_packages_fetches_newest_from_multiple_sources(self):
        old_source_packages = [DummyFetchedPackage("bar", "1.0")]
        new_source_packages = [DummyFetchedPackage("bar", "1.1")]
        old_source = self.useFixture(AptSourceFixture(old_source_packages))
        new_source = self.useFixture(AptSourceFixture(new_source_packages))
        fetcher = self.get_fetcher([old_source, new_source])
        fetched = fetcher.fetch_packages(["bar"])
        self.assertEqual(new_source_packages[0], fetched[0])

    def test_fetch_packages_records_correct_architecture(self):
        available_package = DummyFetchedPackage(
            "foo", "1.0", architecture="nonexistant")
        source = self.useFixture(AptSourceFixture([available_package]))
        fetcher = self.get_fetcher([source], architecture="nonexistant")
        self.assertEqual(
            "nonexistant", fetcher.fetch_packages(["foo"])[0].architecture)

    def test_fetch_packages_fetches_from_correct_architecture(self):
        wanted_package = DummyFetchedPackage(
            "foo", "1.0", architecture="arch1")
        unwanted_package = DummyFetchedPackage(
            "foo", "1.1", architecture="arch2")
        source = self.useFixture(
            AptSourceFixture([wanted_package, unwanted_package]))
        fetcher = self.get_fetcher([source], architecture="arch1")
        self.assertEqual(
            wanted_package, fetcher.fetch_packages(["foo"])[0])

    def test_fetch_packages_fetches_with_relationships(self):
        depends = "foo"
        pre_depends = "bar (>= 1.0)"
        conflicts = "baz | zap"
        recommends = "zing, zang"
        dependency_packages = [
            DummyFetchedPackage("foo", "1.0"),
            DummyFetchedPackage("bar", "1.0"),
            DummyFetchedPackage("baz", "1.0"),
            DummyFetchedPackage("zap", "1.0"),
            DummyFetchedPackage("zing", "1.0"),
            DummyFetchedPackage("zang", "1.0"),
        ]
        wanted_package = DummyFetchedPackage(
            "top", "1.0", depends=depends, pre_depends=pre_depends,
            conflicts=conflicts, recommends=recommends)
        source = self.useFixture(
            AptSourceFixture([wanted_package] + dependency_packages))
        fetcher = self.get_fetcher([source])
        self.assertIn(
            wanted_package, fetcher.fetch_packages(["top"]))

    def test_fetch_packages_download_content_False_doesnt_set_content(self):
        available_package = DummyFetchedPackage("foo", "1.0")
        source = self.useFixture(AptSourceFixture([available_package]))
        fetcher = self.get_fetcher([source])
        fetched_package = fetcher.fetch_packages(
            ["foo"], download_content=False)[0]
        self.assertIs(None, fetched_package.content)

    def test_fetches_dependencies(self):
        wanted_package1 = DummyFetchedPackage("foo", "1.0", depends="bar")
        wanted_package2 = DummyFetchedPackage("bar", "1.0")
        source = self.useFixture(
            AptSourceFixture([wanted_package1, wanted_package2]))
        fetcher = self.get_fetcher([source])
        self.assertEqual(
            [wanted_package1, wanted_package2],
            fetcher.fetch_packages(["foo"]))

    def test_fetches_recommends(self):
        wanted_package1 = DummyFetchedPackage("foo", "1.0", recommends="bar")
        wanted_package2 = DummyFetchedPackage("bar", "1.0")
        source = self.useFixture(
            AptSourceFixture([wanted_package1, wanted_package2]))
        fetcher = self.get_fetcher([source])
        self.assertEqual(
            [wanted_package1, wanted_package2],
            fetcher.fetch_packages(["foo"]))

    def test_broken_dependencies(self):
        wanted_package = DummyFetchedPackage("foo", "1.0", depends="bar")
        source = self.useFixture(AptSourceFixture([wanted_package]))
        fetcher = self.get_fetcher([source])
        e = self.assertRaises(
            DependencyNotSatisfied, fetcher.fetch_packages, ["foo"])
        self.assertEqual(
            "Unable to satisfy dependencies of foo", str(e))

    def test_fetch_packages_leaves_no_marked_changes(self):
        wanted_package = DummyFetchedPackage("foo", "1.0")
        source = self.useFixture(AptSourceFixture([wanted_package]))
        fetcher = self.get_fetcher([source])
        fetcher.fetch_packages(["foo"])
        self.assertEqual([], list(fetcher.cache.cache.get_changes()))

    def test_ignore_with_provides(self):
        ignored_package = DummyFetchedPackage(
            "ubuntu-minimal", "1.0", depends="apt-utils")
        middle_package = DummyFetchedPackage(
            "apt-utils", "1.0", depends="libapt-pkg")
        provides_package = DummyFetchedPackage(
            "apt", "1.0", provides="libapt-pkg", replaces="someotherpackage")
        source = self.useFixture(
            AptSourceFixture(
                [ignored_package, middle_package, provides_package]))
        fetcher = self.get_fetcher([source])
        fetcher.ignore_packages(["ubuntu-minimal"])

    def test_download_content_False_fetches_no_dependencies(self):
        wanted_package1 = DummyFetchedPackage("foo", "1.0", depends="bar")
        wanted_package2 = DummyFetchedPackage("bar", "1.0")
        source = self.useFixture(
            AptSourceFixture([wanted_package1, wanted_package2]))
        fetcher = self.get_fetcher([source])
        self.assertEqual(
            1, len(fetcher.fetch_packages(["foo"], download_content=False)))

    def test_ignore_packages(self):
        wanted_package = DummyFetchedPackage("foo", "1.0", depends="bar")
        ignored_package = DummyFetchedPackage("bar", "1.0")
        source = self.useFixture(
            AptSourceFixture([wanted_package, ignored_package]))
        fetcher = self.get_fetcher([source])
        fetcher.ignore_packages(["bar"])
        self.assertEqual(
            [wanted_package], fetcher.fetch_packages(["foo"]))

    def test_ignore_dependency_of_ignored(self):
        wanted_package = DummyFetchedPackage("foo", "1.0", depends="baz")
        ignored_package = DummyFetchedPackage("bar", "1.0", depends="baz")
        dependency = DummyFetchedPackage("baz", "1.0")
        source = self.useFixture(
            AptSourceFixture([wanted_package, ignored_package, dependency]))
        fetcher = self.get_fetcher([source])
        fetcher.ignore_packages(["bar"])
        self.assertEqual(
            [wanted_package], fetcher.fetch_packages(["foo"]))

    def test_ignore_unknown_package(self):
        source = self.useFixture(AptSourceFixture([]))
        fetcher = self.get_fetcher([source])
        self.assertRaises(KeyError, fetcher.ignore_packages, ["unknown"])

    def test_ignore_cant_satisfy_depenencies(self):
        wanted_package = DummyFetchedPackage("foo", "1.0", depends="bar")
        source = self.useFixture(AptSourceFixture([wanted_package]))
        fetcher = self.get_fetcher([source])
        e = self.assertRaises(
            DependencyNotSatisfied, fetcher.ignore_packages, ["foo"])
        self.assertEqual(
            "Unable to satisfy dependencies of foo", str(e))

    def test_ignored_arent_fetched_even_if_explicitly_requested(self):
        wanted_package = DummyFetchedPackage("foo", "1.0")
        source = self.useFixture(
            AptSourceFixture([wanted_package]))
        fetcher = self.get_fetcher([source])
        fetcher.ignore_packages(["foo"])
        self.assertEqual(
            [], fetcher.fetch_packages(["foo"]))

    def test_no_metadata_for_ignored_even_if_explicitly_requested(self):
        wanted_package = DummyFetchedPackage("foo", "1.0")
        source = self.useFixture(
            AptSourceFixture([wanted_package]))
        fetcher = self.get_fetcher([source])
        fetcher.ignore_packages(["foo"])
        self.assertEqual(
            [], fetcher.fetch_packages(["foo"], download_content=False))

    def test_ignore_is_cumalative(self):
        package1 = DummyFetchedPackage("foo", "1.0")
        package2 = DummyFetchedPackage("bar", "1.0")
        source = self.useFixture(
            AptSourceFixture([package1, package2]))
        fetcher = self.get_fetcher([source])
        fetcher.ignore_packages(["foo"])
        fetcher.ignore_packages(["bar"])
        self.assertEqual(
            [],
            fetcher.fetch_packages(["foo", "bar"], download_content=False))

    def test_ignore_leaves_no_marked_changes(self):
        package1 = DummyFetchedPackage("foo", "1.0")
        source = self.useFixture(AptSourceFixture([package1]))
        fetcher = self.get_fetcher([source])
        fetcher.ignore_packages(["foo"])
        self.assertEqual(
            [],
            list(fetcher.cache.cache.get_changes()))
