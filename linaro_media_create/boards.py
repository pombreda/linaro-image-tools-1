# Copyright (C) 2010, 2011 Linaro
#
# Author: Guilherme Salgado <guilherme.salgado@linaro.org>
#
# This file is part of Linaro Image Tools.
#
# Linaro Image Tools is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Linaro Image Tools is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Linaro Image Tools.  If not, see <http://www.gnu.org/licenses/>.

"""Configuration for boards supported by linaro-media-create.

To add support for a new board, you need to create a subclass of
BoardConfig, set appropriate values for its variables and add it to
board_configs at the bottom of this file.
"""

import atexit
import glob
import os
import re
import tempfile

from linaro_media_create import cmd_runner

# Notes:
# * geometry is currently always 255 heads and 63 sectors due to limitations of
#   older OMAP3 boot ROMs
# * we want partitions aligned on 4 MiB as to get the best performance and
#   limit wear-leveling
# * partitions should preferably end on cylinder boundaries, at least to please
#   sfdisk but also just to have them as big as possible
# * this assumes that root partition follows the boot partition which follows
#   an optional bootloader partition
# * image_size is passed on the command-line and should preferably be a power
#   of 2; it should be used as a "don't go over this size" information for a
#   real device, and a "give me a file exactly this big" requirement for an
#   image file.  Having exactly a power of 2 helps with QEMU; there seem to be
#   some truncating issues otherwise. XXX to be researched

# number of sectors of 512 bytes that we align the start of partitions on; we
# align on 4 MiB
PART_ALIGN_S = 4 * 1024 * 1024 / 512
# start sector of optional bootloader partition, +2s; this is just after MBR
# and partition table; this partition needs not be aligned
LOADER_PART_START_S = 2
# start sector of boot partition, +8 MiB; +4 MiB would still be in the first
# cylinder
BOOT_PART_START_S = 8 * 1024 * 1024 / 512
assert BOOT_PART_START_S / PART_ALIGN_S * PART_ALIGN_S == BOOT_PART_START_S
# start sector of root partition, +64 MiB; means boot partition is roughly
# 56 MiB; XXX there's currently no way to set the relative sizes of boot and
# root partitions
ROOT_PART_START_S = 64 * 1024 * 1024 / 512
assert ROOT_PART_START_S / PART_ALIGN_S * PART_ALIGN_S == ROOT_PART_START_S
BOOT_PART_START_CYL = BOOT_PART_START_S / (63 * 255)
LOADER_PART_SIZE_S = BOOT_PART_START_CYL * (63 * 255) - LOADER_PART_START_S
assert LOADER_PART_START_S + LOADER_PART_SIZE_S < BOOT_PART_START_S
ROOT_PART_START_CYL = ROOT_PART_START_S / (63 * 255)
BOOT_PART_SIZE_S = ROOT_PART_START_CYL * (63 * 255) - BOOT_PART_START_S
assert BOOT_PART_START_S + BOOT_PART_SIZE_S < ROOT_PART_START_S


class BoardConfig(object):
    """The configuration used when building an image for a board."""
    # These attributes may not need to be redefined on some subclasses.
    uboot_flavor = None
    mmc_option = '0:1'
    mmc_part_offset = 0
    fat_size = 32
    extra_serial_opts = ''
    live_serial_opts = ''
    extra_boot_args_options = None

    # These attributes must be defined on all subclasses.
    kernel_addr = None
    initrd_addr = None
    load_addr = None
    kernel_suffix = None
    boot_script = None
    serial_tty = None

    @classmethod
    def get_sfdisk_cmd(cls):
        """Return the sfdisk command to partition the media."""
        if cls.fat_size == 32:
            partition_type = '0x0C'
        else:
            partition_type = '0x0E'

        # This will create a boot partition of type partition_type at offset
        # (in sectors) BOOT_PART_START_S and of size BOOT_PART_SIZE_S followed
        # by a root partition of the default type (Linux) at offset (in
        # sectors) ROOT_PART_START_S filling the remaining space
        # XXX we should honor the specified image size by specifying a
        # corresponding root partition size
        return '%s,%s,%s,*\n%s,,,-' % (
            BOOT_PART_START_S, BOOT_PART_SIZE_S, partition_type,
            ROOT_PART_START_S,
            )

    @classmethod
    def _get_boot_cmd(cls, is_live, is_lowmem, consoles, rootfs_uuid):
        """Get the boot command for this board.

        In general subclasses should not have to override this.
        """
        boot_args_options = 'rootwait ro'
        if cls.extra_boot_args_options is not None:
            boot_args_options += ' %s' % cls.extra_boot_args_options
        serial_opts = ''
        if consoles is not None:
            for console in consoles:
                serial_opts += ' console=%s' % console

            # XXX: I think this is not needed as we have board-specific
            # serial options for when is_live is true.
            if is_live:
                serial_opts += ' serialtty=%s' % cls.serial_tty

        serial_opts += ' %s' % cls.extra_serial_opts

        lowmem_opt = ''
        boot_snippet = 'root=UUID=%s' % rootfs_uuid
        if is_live:
            serial_opts += ' %s' % cls.live_serial_opts
            boot_snippet = 'boot=casper'
            if is_lowmem:
                lowmem_opt = 'only-ubiquity'

        replacements = dict(
            mmc_option=cls.mmc_option, kernel_addr=cls.kernel_addr,
            initrd_addr=cls.initrd_addr, serial_opts=serial_opts,
            lowmem_opt=lowmem_opt, boot_snippet=boot_snippet,
            boot_args_options=boot_args_options)
        return (
            "setenv bootcmd 'fatload mmc %(mmc_option)s %(kernel_addr)s "
                "uImage; fatload mmc %(mmc_option)s %(initrd_addr)s uInitrd; "
                "bootm %(kernel_addr)s %(initrd_addr)s'\n"
            "setenv bootargs '%(serial_opts)s %(lowmem_opt)s "
                "%(boot_snippet)s %(boot_args_options)s'\n"
            "boot" % replacements)

    @classmethod
    def make_boot_files(cls, uboot_parts_dir, is_live, is_lowmem, consoles,
                        root_dir, rootfs_uuid, boot_dir, boot_script,
                        boot_device_or_file):
        boot_cmd = cls._get_boot_cmd(
            is_live, is_lowmem, consoles, rootfs_uuid)
        cls._make_boot_files(
            uboot_parts_dir, boot_cmd, root_dir, boot_dir, boot_script,
            boot_device_or_file)

    @classmethod
    def _make_boot_files(cls, uboot_parts_dir, boot_cmd, root_dir, boot_dir,
                         boot_script, boot_device_or_file):
        """Make the necessary boot files for this board.

        This is usually board-specific so ought to be defined in every
        subclass.
        """
        raise NotImplementedError()


class classproperty(object):
    """A descriptor that provides @property behavior on class methods."""
    def __init__(self, getter):
        self.getter = getter
    def __get__(self, instance, cls):
        return self.getter(cls)


class OmapConfig(BoardConfig):

    # XXX: Here we define these things as dynamic properties because our
    # temporary hack to fix bug 697824 relies on changing the board's
    # serial_tty at run time.
    _extra_serial_opts = None
    _live_serial_opts = None
    _serial_tty = None

    @classproperty
    def serial_tty(cls):
        # This is just to make sure no callsites use .serial_tty before
        # calling set_appropriate_serial_tty(). If we had this in the first
        # place we'd have uncovered bug 710971 before releasing.
        raise AttributeError(
            "You must not use this attribute before calling "
            "set_appropriate_serial_tty")

    @classproperty
    def live_serial_opts(cls):
        return cls._live_serial_opts % cls.serial_tty

    @classproperty
    def extra_serial_opts(cls):
        return cls._extra_serial_opts % cls.serial_tty

    @classmethod
    def set_appropriate_serial_tty(cls, chroot_dir):
        """Set the appropriate serial_tty depending on the kernel used.

        If the kernel found in the chroot dir is << 2.6.36 we use tyyS2, else
        we use the default value (_serial_tty).
        """
        # XXX: This is also part of our temporary hack to fix bug 697824.
        cls.serial_tty = classproperty(lambda cls: cls._serial_tty)
        vmlinuz = _get_file_matching(
            os.path.join(chroot_dir, 'boot', 'vmlinuz*'))
        basename = os.path.basename(vmlinuz)
        minor_version = re.match('.*2\.6\.([0-9]{2}).*', basename).group(1)
        if int(minor_version) < 36:
            cls.serial_tty = classproperty(lambda cls: 'ttyS2')

    @classmethod
    def make_boot_files(cls, uboot_parts_dir, is_live, is_lowmem, consoles,
                        root_dir, rootfs_uuid, boot_dir, boot_script,
                        boot_device_or_file):
        # XXX: This is also part of our temporary hack to fix bug 697824; we
        # need to call set_appropriate_serial_tty() before doing anything that
        # may use cls.serial_tty.
        cls.set_appropriate_serial_tty(root_dir)
        super(OmapConfig, cls).make_boot_files(
            uboot_parts_dir, is_live, is_lowmem, consoles, root_dir,
            rootfs_uuid, boot_dir, boot_script, boot_device_or_file)

    @classmethod
    def _make_boot_files(cls, uboot_parts_dir, boot_cmd, chroot_dir,
                         boot_dir, boot_script, boot_device_or_file):
        install_omap_boot_loader(chroot_dir, boot_dir)
        make_uImage(
            cls.load_addr, uboot_parts_dir, cls.kernel_suffix, boot_dir)
        make_uInitrd(uboot_parts_dir, cls.kernel_suffix, boot_dir)
        make_boot_script(boot_cmd, boot_script)
        make_boot_ini(boot_script, boot_dir)


class BeagleConfig(OmapConfig):
    uboot_flavor = 'omap3_beagle'
    _serial_tty = 'ttyO2'
    _extra_serial_opts = 'console=tty0 console=%s,115200n8'
    _live_serial_opts = 'serialtty=%s'
    kernel_addr = '0x80000000'
    initrd_addr = '0x81600000'
    load_addr = '0x80008000'
    kernel_suffix = 'linaro-omap'
    boot_script = 'boot.scr'
    extra_boot_args_options = (
        'earlyprintk fixrtc nocompcache vram=12M '
        'omapfb.mode=dvi:1280x720MR-16@60')


class OveroConfig(OmapConfig):
    uboot_flavor = 'omap3_overo'
    _serial_tty = 'ttyO2'
    _extra_serial_opts = 'console=tty0 console=%s,115200n8'
    kernel_addr = '0x80000000'
    initrd_addr = '0x81600000'
    load_addr = '0x80008000'
    kernel_suffix = 'linaro-omap'
    boot_script = 'boot.scr'
    extra_boot_args_options = (
        'earlyprintk')


class PandaConfig(OmapConfig):
    uboot_flavor = 'omap4_panda'
    _serial_tty = 'ttyO2'
    _extra_serial_opts = 'console=tty0 console=%s,115200n8'
    _live_serial_opts = 'serialtty=%s'
    kernel_addr = '0x80200000'
    initrd_addr = '0x81600000'
    load_addr = '0x80008000'
    kernel_suffix = 'linaro-omap'
    boot_script = 'boot.scr'
    extra_boot_args_options = (
        'earlyprintk fixrtc nocompcache vram=32M '
        'omapfb.vram=0:8M mem=463M ip=none')


class IgepConfig(BeagleConfig):
    uboot_flavor = None

    @classmethod
    def _make_boot_files(cls, uboot_parts_dir, boot_cmd, chroot_dir,
                         boot_dir, boot_script, boot_device_or_file):
        make_uImage(
            cls.load_addr, uboot_parts_dir, cls.kernel_suffix, boot_dir)
        make_uInitrd(uboot_parts_dir, cls.kernel_suffix, boot_dir)
        make_boot_script(boot_cmd, boot_script)
        make_boot_ini(boot_script, boot_dir)


class Ux500Config(BoardConfig):
    serial_tty = 'ttyAMA2'
    extra_serial_opts = 'console=tty0 console=%s,115200n8' % serial_tty
    live_serial_opts = 'serialtty=%s' % serial_tty
    kernel_addr = '0x00100000'
    initrd_addr = '0x08000000'
    load_addr = '0x00008000'
    kernel_suffix = 'ux500'
    boot_script = 'flash.scr'
    extra_boot_args_options = (
        'earlyprintk rootdelay=1 fixrtc nocompcache '
        'mem=96M@0 mem_modem=32M@96M mem=44M@128M pmem=22M@172M '
        'mem=30M@194M mem_mali=32M@224M pmem_hwb=54M@256M '
        'hwmem=48M@302M mem=152M@360M')
    mmc_option = '1:1'

    @classmethod
    def _make_boot_files(cls, uboot_parts_dir, boot_cmd, chroot_dir,
                         boot_dir, boot_script, boot_device_or_file):
        make_uImage(
            cls.load_addr, uboot_parts_dir, cls.kernel_suffix, boot_dir)
        make_uInitrd(uboot_parts_dir, cls.kernel_suffix, boot_dir)
        make_boot_script(boot_cmd, boot_script)


class Mx51evkConfig(BoardConfig):
    serial_tty = 'ttymxc0'
    extra_serial_opts = 'console=tty0 console=%s,115200n8' % serial_tty
    live_serial_opts = 'serialtty=%s' % serial_tty
    kernel_addr = '0x90000000'
    initrd_addr = '0x90800000'
    load_addr = '0x90008000'
    kernel_suffix = 'linaro-mx51'
    boot_script = 'boot.scr'
    mmc_part_offset = 1
    mmc_option = '0:2'

    @classmethod
    def get_sfdisk_cmd(cls):
        # Create a one cylinder partition for fixed-offset bootloader data at
        # the beginning of the image (size is one cylinder, so 8224768 bytes
        # with the first sector for MBR).
        sfdisk_cmd = super(Mx51evkConfig, cls).get_sfdisk_cmd()
        return '%s,%s,0xDA\n%s' % (
            LOADER_PART_START_S, LOADER_PART_SIZE_S, sfdisk_cmd,
            )

    @classmethod
    def _make_boot_files(cls, uboot_parts_dir, boot_cmd, chroot_dir,
                         boot_dir, boot_script, boot_device_or_file):
        uboot_file = os.path.join(
            chroot_dir, 'usr', 'lib', 'u-boot', 'mx51evk', 'u-boot.imx')
        install_mx51evk_boot_loader(uboot_file, boot_device_or_file)
        make_uImage(
            cls.load_addr, uboot_parts_dir, cls.kernel_suffix, boot_dir)
        make_uInitrd(uboot_parts_dir, cls.kernel_suffix, boot_dir)
        make_boot_script(boot_cmd, boot_script)


class VexpressConfig(BoardConfig):
    uboot_flavor = 'ca9x4_ct_vxp'
    serial_tty = 'ttyAMA0'
    extra_serial_opts = 'console=tty0 console=%s,38400n8' % serial_tty
    live_serial_opts = 'serialtty=%s' % serial_tty
    kernel_addr = '0x60008000'
    initrd_addr = '0x81000000'
    load_addr = kernel_addr
    kernel_suffix = 'linaro-vexpress'
    boot_script = None
    # ARM Boot Monitor is used to load u-boot, uImage etc. into flash and
    # only allows for FAT16
    fat_size = 16

    @classmethod
    def _make_boot_files(cls, uboot_parts_dir, boot_cmd, chroot_dir,
                         boot_dir, boot_script, boot_device_or_file):
        make_uImage(
            cls.load_addr, uboot_parts_dir, cls.kernel_suffix, boot_dir)
        make_uInitrd(uboot_parts_dir, cls.kernel_suffix, boot_dir)


board_configs = {
    'beagle': BeagleConfig,
    'igep': IgepConfig,
    'panda': PandaConfig,
    'vexpress': VexpressConfig,
    'ux500': Ux500Config,
    'mx51evk': Mx51evkConfig,
    'overo': OveroConfig,
    }


def _run_mkimage(img_type, load_addr, entry_point, name, img_data, img,
                 stdout=None, as_root=True):
    cmd = ['mkimage',
           '-A', 'arm',
           '-O', 'linux',
           '-T', img_type,
           '-C', 'none',
           '-a', load_addr,
           '-e', load_addr,
           '-n', name,
           '-d', img_data,
           img]
    proc = cmd_runner.run(cmd, as_root=as_root, stdout=stdout)
    proc.wait()
    return proc.returncode


def _get_file_matching(regex):
    """Return a file whose path matches the given regex.

    If zero or more than one files match, raise a ValueError.
    """
    files = glob.glob(regex)
    if len(files) == 1:
        return files[0]
    elif len(files) == 0:
        raise ValueError(
            "No files found matching '%s'; can't continue" % regex)
    else:
        # TODO: Could ask the user to chosse which file to use instead of
        # raising an exception.
        raise ValueError("Too many files matching '%s' found." % regex)


def make_uImage(load_addr, uboot_parts_dir, suffix, boot_disk):
    img_data = _get_file_matching(
        '%s/vmlinuz-*-%s' % (uboot_parts_dir, suffix))
    img = '%s/uImage' % boot_disk
    return _run_mkimage(
        'kernel', load_addr, load_addr, 'Linux', img_data, img)


def make_uInitrd(uboot_parts_dir, suffix, boot_disk):
    img_data = _get_file_matching(
        '%s/initrd.img-*-%s' % (uboot_parts_dir, suffix))
    img = '%s/uInitrd' % boot_disk
    return _run_mkimage('ramdisk', '0', '0', 'initramfs', img_data, img)


def make_boot_script(boot_script_data, boot_script):
    # Need to save the boot script data into a file that will be passed to
    # mkimage.
    _, tmpfile = tempfile.mkstemp()
    atexit.register(os.unlink, tmpfile)
    with open(tmpfile, 'w') as fd:
        fd.write(boot_script_data)
    return _run_mkimage(
        'script', '0', '0', 'boot script', tmpfile, boot_script)


def install_mx51evk_boot_loader(imx_file, boot_device_or_file):
    proc = cmd_runner.run([
        "dd",
        "if=%s" % imx_file,
        "of=%s" % boot_device_or_file,
        "bs=1024",
        "seek=1",
        "conv=notrunc"], as_root=True)
    proc.wait()


def _get_mlo_file(chroot_dir):
    # XXX bug=702645: This is a temporary solution to make sure l-m-c works
    # with any version of x-loader-omap. The proper solution is to have
    # hwpacks specify the location of the MLO file or include just the MLO
    # file instead of an x-loader-omap package.
    # This pattern matches the path of MLO files installed by the latest
    # x-loader-omap package (e.g. /usr/lib/x-loader/<version>/MLO)
    files = glob.glob(
        os.path.join(chroot_dir, 'usr', 'lib', '*', '*', 'MLO'))
    if len(files) == 0:
        # This one matches the path of MLO files installed by older
        # x-loader-omap package (e.g. /usr/lib/x-loader-omap[34]/MLO)
        files = glob.glob(
            os.path.join(chroot_dir, 'usr', 'lib', '*', 'MLO'))
    if len(files) == 1:
        return files[0]
    elif len(files) > 1:
        raise AssertionError(
            "More than one MLO file found on %s" % chroot_dir)
    else:
        raise AssertionError("No MLO files found on %s" % chroot_dir)


def install_omap_boot_loader(chroot_dir, boot_disk):
    mlo_file = _get_mlo_file(chroot_dir)
    cmd_runner.run(["cp", "-v", mlo_file, boot_disk], as_root=True).wait()
    # XXX: Is this really needed?
    cmd_runner.run(["sync"]).wait()


def make_boot_ini(boot_script, boot_disk):
    proc = cmd_runner.run(
        ["cp", "-v", boot_script, "%s/boot.ini" % boot_disk], as_root=True)
    proc.wait()
