#!/usr/bin/env python3.5
# *-* coding: utf-8 *-*

from functools import reduce
from operator import add
from os import getlogin
from pathlib import Path
from random import seed, choice
from string import ascii_letters, digits
from subprocess import check_output, CalledProcessError

import progressbar
from progressbar.utils import get_terminal_size

from common.util import byte_len

# Some useful info about eCryptfs filename lengths:
# http://unix.stackexchange.com/questions/32795/what-is-the-maximum-allowed-filename-and-folder-size-with-ecryptfs

seed()
REACHED_MAX = False
MAX_FILENAME_LEN = 150
NUM_ITERS = 10000
ALPHABET = ascii_letters + digits + '-._ ' + ''.join([chr(x) for x in [0x263f, 0x1f710, 0x1f63a, 0x41]])
TOTAL_JOBS = reduce(add,
                    [sorted([NUM_ITERS, (len(ALPHABET) ** x)])[0] for x in range(1, MAX_FILENAME_LEN+1)])


class Test:
    """Test file name lengths in eCryptfs.

    This test determines the ranges of file name lengths in the upper
    filesystem produce which lengths of lower filesystem file names. It does
    this by creating a file in the upper filesystem, finding the corresponding
    file in the lower filesystem, and records the lengths of each. It
    iteratively increases the length of the upper filesystem file name after
    testing each distinct length many times (NUM_ITERS).

    Results are printed to stdout.
    """

    def __init__(self):
        # Create single dir in ~ dir (upper directory), find its inode number, then find the corresponding encrypted
        # file by matching the inode number against the one just obtained
        self.upper_dir = Path('~/dbling_delete_me').expanduser()
        self.upper_dir.mkdir(exist_ok=True)
        self.inode = self.upper_dir.stat().st_ino

        self.lower_dir = find_lower(self.inode, Path('/home/.ecryptfs') / getlogin() / '.Private')

        self.results = dict.fromkeys(
            [(x, 84) for x in range(2, 16)] +
            [(x, 104) for x in range(17, 32)] +
            [(x, 124) for x in range(33, 48)] +
            [(x, 148) for x in range(49, 64)] +
            [(x, 168) for x in range(65, 80)] +
            [(x, 188) for x in range(81, 96)] +
            [(x, 212) for x in range(97, 112)] +
            [(x, 232) for x in range(113, 128)] +
            [(x, 252) for x in range(129, 140)],
            True
        )

    def start(self):
        """Start the test."""
        # Initialize the progress bar
        bar = progressbar.ProgressBar(max_value=TOTAL_JOBS,
                                      redirect_stdout=True,
                                      widgets=[
                                          ' ', progressbar.Percentage(), ' ',
                                          progressbar.Bar('=', '[', '] '),
                                          # progressbar.Counter(), ' / ', str(TOTAL_JOBS), ' ',
                                          progressbar.Timer('%(elapsed)s'),
                                          ' / ',
                                          progressbar.AdaptiveETA(),
                                          # progressbar.ETA(),
                                          # progressbar.AbsoluteETA(),
                                          # ' ', progressbar.SimpleProgress(),
                                      ])
        snip = ' (snip)'
        n = 0
        failed_filenames = 0
        for name in letters():
            # Create the file name
            n += 1
            upper = self.upper_dir / name

            # In the upper directory, create files with increasing length
            try:
                upper.touch()
            except OSError:
                # Happens when the name is too long for the filesystem
                print('File name of length {} (bytes) is too long. Stopping.'.format(byte_len(name)))
                break

            # In the lower directory, monitor the length of the encrypted filename
            try:
                lower = find_lower(upper.stat().st_ino, self.lower_dir)
            except CalledProcessError:
                # Usually this means the file name '.' was attempted. No big deal, just move along.
                failed_filenames += 1
                continue

            # Lower file names will always use ASCII characters, so we don't need to use byte_len() for it
            pair = (byte_len(name), len(lower.name))

            try:
                if not n % 50:
                    # Only update every fifty operations to help the time estimate not be so erratic
                    bar.update(n)
            except ValueError:
                # If the value of n is greater than the bar is expecting as a maximum, it will complain
                pass

            # If we haven't seen an upper name of this length yield a lower name of this length, add it to the results
            if not self.results.get(pair):
                self.results[pair] = name
                # Here we're dealing with the number of printing characters, not the bytes needed to store them
                max_width = get_terminal_size()[0] - 28 - len(snip)  # Yes, we really want to compute this each time
                if len(name) > max_width:
                    name = name[:max_width + 1] + snip
                print('{:4} --> {:4}   Upper name: {}'.format(*pair, name))

            # Delete the file now that we're done with it
            upper.unlink()

        bar.finish()
        if failed_filenames:
            print('Completed work even though I had {} failed filenames'.format(failed_filenames))


def letters(length=1):
    """Generate words NUM_ITERS times, up to MAX_FILENAME_LEN long.

    Intelligently determines when NUM_ITERS is greater than the total possible
    combinations of the alphabet being used (which would cause useless
    repetition) and defers to the lesser of these two values.

    :param int length: Desired length of a word for this level of iteration.
        When the function calls itself, this will be incremented until it is
        greater than MAX_FILENAME_LEN.

        .. note:: This length refers to the number of *characters* in the word,
                  **not** the number of *bytes* the word uses, which is an
                  important distinction in this setting.
    :return: As a generator, this should be used in a `for` loop. Yields words
        that are `length` long, `NUM_ITERS` times before incrementing `length`
        and continuing until `MAX_FILENAME_LEN` is reached.
    :rtype: str
    """
    if length > MAX_FILENAME_LEN:
        return  # Stop recursing

    for l in range(sorted([NUM_ITERS, (len(ALPHABET) ** length)])[0]):
        yield ''.join([choice(ALPHABET) for _ in range(length)])

    # Increase the length, continue iterating
    yield from letters(length+1)


def find_lower(inode, parent):
    """Return the file name in the `parent` dir with the given inode number.

    Depends on the Unix command-line utilities `ls` and `grep`, so this is
    *not* cross-platform compatible.

    :param int inode: The inode number of the file to find.
    :param Path parent: A :class:`Path` object pointing to the directory where
        the file is located that we're looking for.
    :return: A :class:`Path` object to the file.
    :rtype: Path
    """
    command = 'ls -i1 {} | grep {}'.format(parent, inode)
    return parent / check_output(command, shell=True).decode('utf-8').strip().split(maxsplit=1)[1]


if __name__ == '__main__':
    Test().start()
