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

SEGMENT_SIZE = '10G'

# Run ewfacquire -h for options
acq_command = ['ewfacquire',  # TODO Need to add either -q or -u?
               '-B %d' % len_of_partition,  # In bytes
               '-o %d' % partition_offset,  # Might be in bytes?
               '-c fast',  # Compression should be the fastest, not the best
               '-f encase6',  # Format of the EWF file
               '-S %s' % SEGMENT_SIZE,  # EWF file will be split into segments of this size
               '-t %s' % output_file,  # Without the file extension
               '%s' % target_device]  # Path to the device



dfxml_command = ['fiwalk',
                 '-g',  # Don't get the file data, just metadata
                 '-z',  # Don't calculate checksums for the files
                 '-G0',  # Process files of all sizes
                 '-x',  # Output to stdout (only way to not get the DTD)
                 '%s' % output_file,  # Disk image
                 '> %s' % output_dfxml]  # DFXML file output
