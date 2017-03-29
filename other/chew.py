#!/usr/bin/env python3
"""
Usage: chew [-q|-u] [-x] [-e] [-v] TARGET_DEVICE [OUTPUT_FILE]

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

import logging
import subprocess
from datetime import datetime
from os import path

from docopt import docopt

import pyuefi

SEGMENT_SIZE = '10G'
SECTOR_SIZE = 512


class Chew(object):
    """

    """

    def __init__(self, dev, auto_run=False, dd=False, dfxml=None, confirm=False):
        self.dev = dev

        # Use pyuefi to get the STATE partition data
        self.uefi = pyuefi.PyUEFI(self.dev)
        self.partition = self.uefi.get_part_by_name('STATE')
        self.lba_start = self.partition['lba_start']
        self.lba_end = self.partition['lba_end']
        self.state_dev_path = self.partition['dev_path']

        self.now = datetime.now()

        # Create the EWF file
        self._img_dir = path.join(path.dirname(path.realpath(__file__)), '../images/')
        self._dfxml = None
        self._img = None
        if auto_run:
            self.do_acquisition(self.now, dd, confirm)
            if dfxml:
                self.do_dfxml()

    def do_acquisition(self, stamp=None, dd=False, confirm=False):
        """
        Try acquisition with ewfacquire first, then use dd if it fails.

        :param stamp: Time stamp to append to the image name.
        :type stamp: datetime
        :return: The file name of the image. (full path, with file extension)
        :rtype: str
        """
        if not dd:
            try:
                self._img = self._do_ewf_acquisition(stamp)
            except ChildProcessError:
                dd = True
        if dd:
            self._img = self._do_dd_acquisition(stamp, confirm)
        return self._img

    def _do_dd_acquisition(self, stamp=None, confirm=False):
        """
        Call dd as a subprocess.

        :param stamp: Time stamp to append to the image name.
        :type stamp: datetime
        :return: The file name of the image. (full path, with file extension)
        :rtype: str
        """
        # Here we're using sectors to reference the start and length
        len_of_partition = (self.lba_end - self.lba_start + 1)
        partition_offset = self.lba_start

        # Generate the image's file name (full path, with file extension)
        try:
            image_file = self.uefi.uefi_header['disk_guid'] + stamp.strftime('_%Y%m%d_%H%M%S')
        except NameError or AttributeError:
            # stamp was None or an unsupported object
            image_file = self.uefi.uefi_header['disk_guid']
        image_file = path.join(self._img_dir, image_file + '.img')

        if self.state_dev_path is None:
            args = 'sudo dd if={source:s} of={dest:s} skip={offset:d} count={num_blocks:d} ibs={bs:d} obs={bs:d}'
            args = args.format(source=self.dev,
                               dest=image_file,
                               offset=partition_offset,
                               num_blocks=len_of_partition,
                               bs=SECTOR_SIZE)
        else:
            logging.info('Determined that the STATE partition is located at %s' % self.state_dev_path)
            args = 'sudo dd if={source:s} of={dest:s}'.format(source=self.state_dev_path, dest=image_file)

        if confirm:
            print('About to execute the following command:')
            print(args)
            yn = input('\nWould you like to proceed? [y/N] ')
            if len(yn) and yn[0].lower() == 'y':
                pass
            else:
                print('Cancelling.\n')
                exit(1)

        # Not sure if we need to pipe any I/O
        mbytes = len_of_partition*SECTOR_SIZE/(1024*1024)
        logging.info("Acquiring STATE partition using dd. ({:,.1f} MB)".format(mbytes))
        proc = subprocess.call(args, shell=True)  # Should return 0
        if proc:
            # TODO Call didn't go well. Handle this.
            print("Acquisition returned the following code:")
            print(proc)
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
        args = ['sudo', 'ewfacquire',  # TODO Need to add either -q or -u?
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
        if proc:
            # TODO Call didn't go well. Handle this.
            raise ChildProcessError

        # Add the file extension before returning
        return image_file + '.E01'

    def do_dfxml(self, image_file=None):
        """
        Create DFXML file from the drive's image.

        :param image_file: The file name of the image. (full path, with file extension)
        :type image_file: str
        :return: The file name of the DFXML file created
        :rtype: str
        """
        if image_file is None:
            image_file = self._img
        # Remove everything after and including the last period in the filename
        _img = image_file.rsplit('.', 1)[0]
        self._dfxml = _img + '.df.xml'

        args = 'fiwalk -g -z -O -G0 -x %s > %s' % (image_file, self._dfxml)
        # -g    Don't get the file data, just metadata
        # -z    Don't calculate checksums for the files
        # -O    Only walk allocated files
        # -G0   Process files of all sizes
        # -x    Output to stdout (only way to not get the DTD)
        # %s    Disk image
        # > %s  DFXML file output

        # Not sure if we need to pipe any I/O
        proc = subprocess.call(args, shell=True)
        if proc:
            # TODO Call didn't go well. Handle this.
            raise ChildProcessError
        return self._dfxml

    @property
    def dfxml(self):
        """
        Get the DFXML file name (full path).

        :return: The file name of the DFXML file.
        :rtype: str
        """
        return self._dfxml


if __name__ == '__main__':
    args = docopt(__doc__)
    c = Chew(args['TARGET_DEVICE'], True, not args['-e'], args['-x'], args['-v'])
