#!/usr/bin/env python
"""
Usage: chew [-q|-u] TARGET_DEVICE [OUTPUT_FILE]

General flow:
1. Using the device string specified by the user, determine if it is a valid
   target (attached device).
2. Run ewfacquire on the target device, running in either quiet mode 
   (option -q), unattended mode (option -u), or neither, depending on the
   user's specification.
3. Run fiwalk on the EWF image and pipe the output to a DFXML file.
4. (If applicable) Generate the differential information between this image
   and the parent image.
"""

from datetime import datetime
from os import path
from . import pyuefi
import subprocess


SEGMENT_SIZE = '10G'
SECTOR_SIZE = 512


class Chew(object):
    """

    """

    def __init__(self, dev):
        self.dev = dev

        # Use pyuefi to get the STATE partition data
        self.uefi = pyuefi.PyUEFI(self.dev)
        self.partition = self.uefi.get_part_by_name('STATE')
        self.lba_start = self.partition['lba_start']
        self.lba_end = self.partition['lba_end']

        self.now = datetime.now()

        # Create the EWF file
        self._img_dir = path.join(path.dirname(path.realpath(__file__)), '../images/')
        self._img = self._do_acquisition(self.now)
        self._dfxml = self._do_dfxml(self._img)

    def _do_acquisition(self, stamp=None):
        """
        Try acquisition with ewfacquire first, then use dd if it fails.

        :param stamp: Time stamp to append to the image name.
        :type stamp: datetime
        :return: The file name of the image. (full path, with file extension)
        :rtype: str
        """
        try:
            return self._do_ewf_acquisition(stamp)
        except ChildProcessError:
            return self._do_dd_acquisition(stamp)

    def _do_dd_acquisition(self, stamp=None):
        """
        Call dd as a subprocess.

        :param stamp: Time stamp to append to the image name.
        :type stamp: datetime
        :return: The file name of the image. (full path, with file extension)
        :rtype: str
        """
        len_of_partition = (self.lba_end - self.lba_start + 1)
        partition_offset = self.lba_start

        # Generate the image's file name (full path, with file extension)
        try:
            image_file = self.uefi.uefi_header['disk_guid'] + stamp.strftime('_%Y%m%d_%H%M%S')
        except NameError or AttributeError:
            # stamp was None or an unsupported object
            image_file = self.uefi.uefi_header['disk_guid']
        image_file = path.join(self._img_dir, image_file + '.img')
        
        # TODO: Figure out all the parameters we want to use for dd
        args = ['dd',
                'if=%s' % self.dev,
                'of=%s' % image_file
                ]

        # Not sure if we need to pipe any I/O
        proc = subprocess.call(args)
        if not proc:
            # TODO Call didn't go well. Handle this.
            raise ChildProcessError

        return image_file

    def _do_ewf_acquisition(self, stamp=None):
        """
        Call ewfacquire as a subprocess.

        :param stamp: Time stamp to append to the image name.
        :type stamp: datetime
        :return: The file name of the image. (full path, with file extension)
        :rtype: str
        """
        len_of_partition = (self.lba_end - self.lba_start + 1) * SECTOR_SIZE  # Inclusive
        partition_offset = self.lba_start * SECTOR_SIZE

        # Generate the image's file name (full path, no file extension)
        try:
            image_file = self.uefi.uefi_header['disk_guid'] + stamp.strftime('_%Y%m%d_%H%M%S')
        except NameError or AttributeError:
            # stamp was None or an unsupported object
            image_file = self.uefi.uefi_header['disk_guid']
        image_file = path.join(self._img_dir, image_file)

        # Run ewfacquire -h for options
        args = ['ewfacquire',  # TODO Need to add either -q or -u?
                '-u',  # Run in unattended mode (no output)
                '-B %d' % len_of_partition,  # In bytes
                '-o %d' % partition_offset,  # In bytes
                '-c fast',  # Compression should be the fastest, not the best
                '-f encase6',  # Format of the EWF file
                '-S %s' % SEGMENT_SIZE,  # EWF file will be split into segments of this size
                '-t %s' % image_file,  # Without the file extension
                '%s' % self.dev]  # Path to the device
        
        # Not sure if we need to pipe any I/O
        proc = subprocess.call(args)
        if not proc:
            # TODO Call didn't go well. Handle this.
            raise ChildProcessError

        # Add the file extension before returning
        return image_file + '.E01'

    def _do_dfxml(self, image_file):
        """
        Create DFXML file from the drive's image.

        :param image_file: The file name of the image. (full path, with file extension)
        :type image_file: str
        :return: The file name of the DFXML file created
        :rtype: str
        """
        # Remove everything after and including the last period in the filename
        _img = image_file.rsplit('.', 1)[0]
        output_dfxml = _img + '.df.xml'

        args = ['fiwalk',
                '-g',  # Don't get the file data, just metadata
                '-z',  # Don't calculate checksums for the files
                '-G0',  # Process files of all sizes
                '-x',  # Output to stdout (only way to not get the DTD)
                '%s' % image_file,  # Disk image
                '> %s' % output_dfxml]  # DFXML file output

        # Not sure if we need to pipe any I/O
        proc = subprocess.call(args)
        if not proc:
            # TODO Call didn't go well. Handle this.
            raise ChildProcessError
        return output_dfxml

    @property
    def dfxml(self):
        """
        Get the DFXML file name (full path).

        :return: The file name of the DFXML file.
        :rtype: str
        """
        return self._dfxml
