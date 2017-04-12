#!/usr/bin/env python3
# *-* coding: utf-8 *-*
import atexit
import logging
import os
from math import e
from operator import itemgetter
from sys import argv as sys_argv

from bs4 import BeautifulSoup
from sqlalchemy import Table, select

from common.centroid import CentroidCalc, get_normalizing_vector, centroid_difference, USED_FIELDS, USED_TO_DB, \
    DB_META, get_tree_top


STARTER = """<?xml version="1.0" encoding="UTF-8"?>
<merl
    xmlns="https://mikemabey.com/schema/merl"
    xmlns:dfxml="http://www.forensicswiki.org/wiki/Category:Digital_Forensics_XML"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
        https://mikemabey.com/schema/merl https://mikemabey.com/schema/merl.xsd
        http://www.forensicswiki.org/wiki/Category:Digital_Forensics_XML https://raw.githubusercontent.com/dfxml-working-group/dfxml_schema/master/dfxml.xsd
    "
/>"""
MAX_FAMILY_MATCHES = 1000
MAX_CANDIDATE_TAGS = 5


class Merl:
    def __init__(self, *, src_image_filename=None, src_mount_point=None, out_fp=None, plain_output=False):
        self._soup = BeautifulSoup(STARTER, 'xml')
        self._top = self._soup.merl

        conn = DB_META.bind.connect()
        self._db_conn = conn
        self._extension = Table('extension', DB_META)
        self._cent_fam = Table('centroid_family', DB_META)
        self._norm_vec = get_normalizing_vector()

        self._cent_cols = [getattr(self._cent_fam.c, USED_TO_DB[x]) for x in (USED_FIELDS + ('_c_size',))] + \
                          [self._cent_fam.c.ttl_files]
        self._centroid_select_fields = self._cent_cols + [self._cent_fam.c.pk]
        self._out_file = None
        self.output_file = out_fp
        self.plain_output = plain_output

        self._make_source_tag(src_image_filename, src_mount_point)
        self._make_creator_tag()

        @atexit.register
        def close_db():
            conn.close()

    @property
    def merl(self):
        return self._soup.prettify()

    @property
    def output_file(self):
        return self._out_file

    @output_file.setter
    def output_file(self, stream):
        if stream is None or hasattr(stream, 'write'):
            self._out_file = stream

    def save_merl(self):
        self.output_file.write(self.merl)
        print(self.merl, file=self.output_file)

    def close_db(self):
        self._db_conn.close()

    def match_candidates(self, candidates_list):
        """Iterate through the list of candidates and find matches.
        
        :param list candidates_list: List of graphs that are candidates for
            being extensions installed on the device.
        :rtype: None
        """
        n = 0
        for c in candidates_list:
            n += 1
            self.match_candidate(c, n)

    def match_candidate(self, candidate, match_num=None):
        """Find all matches for a single candidate.
        
        Depending on how the program was invoked, this will either print the
        results in a plain format with no structure (but that is easier to
        read quickly) or in an XML format conforming to the MERL schema.
        
        :param DblingGraph candidate: A graph that is a candidate for being an
            extension installed on the device.
        :param int match_num: Number indicating which number of candidate this
            is in a set of candidates. Note that this number is not an index,
            since numbering begins at 1.
        :rtype: None
        """
        # Iterate through the centroid families table, and get the centroid for the family
        cent = CentroidCalc(candidate)
        # if cent.size < 30:  # TODO: Remove this. There are legit extensions with only 5 nodes.
        #     logging.debug('Skipping candidate that has only %s vertices.' % cent.size)
        #     return

        try:
            cent.do_calc()
        except (ValueError, ZeroDivisionError):
            logging.warning('Invalid candidate for centroid calculation. Skipping...', exc_info=1)
            return
        # Select only the rows that have the same value for the ttl_files column
        s = select(self._centroid_select_fields).where(self._cent_fam.c.ttl_files == cent.centroid[-1])
        hit = {}

        for fam in self._db_conn.execute(s):
            # Calculate the distance between the candidate and the centroid
            row_cent = tuple([fam[x] for x in self._cent_cols])
            dist = centroid_difference(cent.centroid, row_cent, self._norm_vec)
            pk = fam[self._cent_fam.c.pk]

            # # If the distance is less than the max stored hits, add it, remove the one it bested
            # if len(hit) < MAX_FAMILY_MATCHES:
            hit[pk] = dist
            # else:
            #     for h in hit:
            #         if dist < hit[h]:
            #             hit.pop(h)
            #             hit[pk] = dist
            #             break

        # After iterating, get the data on all the extensions that are part of the top hit families
        hit_entries = []
        for h in hit:
            fam_size = self._db_conn.execute(select([self._cent_fam.c.distinct_id_members]).
                                             where(self._cent_fam.c.pk == h)).fetchone()[0]
            conf = calc_confidence(hit[h], fam_size)
            # print(fam_size, end=' ')

            s_hits = select([self._extension.c.ext_id,
                             self._extension.c.version,
                             # self._extension.c.name,
                             # self._extension.c.vendor,
                             ]).\
                where(self._extension.c.centroid_group == h)
            for ext in self._db_conn.execute(s_hits):
                # TODO: Complete this entry information
                # To do that, we need to parse the manifest files for all the extensions and add the extension name and
                # vendor to the database.
                entry = dict(ext_id=ext[self._extension.c.ext_id],
                             ext_ver=ext[self._extension.c.version],
                             # ext_name='Name unavailable',  # ext[self._extension.c.name],
                             # ext_vendor='Vendor unavailable',  # ext[self._extension.c.vendor],
                             confidence=conf)
                hit_entries.append(entry)

        sorted_hits = sorted(hit_entries, key=itemgetter('confidence'), reverse=True)

        if self.plain_output:
            _n = ''
            if match_num is not None:
                _n = ' (%d)' % match_num
            logging.debug(('Calculated the matches for a candidate graph with %d vertices.' % cent.size) + _n)

            if match_num is not None:
                print('\nC%d Candidate Matches' % match_num, file=self.output_file)
                print('---------------------\n', file=self.output_file)
            else:
                print('\nCandidate Matches', file=self.output_file)
                print('-----------------\n', file=self.output_file)
            n = 0
            for ent in sorted_hits:
                n += 1
                print('#%d' % n, file=self.output_file)
                for k in ent:
                    print('%s: %s' % (k, ent[k]), file=self.output_file)
                print(file=self.output_file)

        else:
            candidate_tags = []
            n = 0
            for ent in sorted_hits:
                # Use list comprehension to make a tag for each of the keys in the entry and set the tag's value to the
                # entry's value for that key. Then expand the list so each tag is its own parameter to tag() for the
                # "candidate" tag.
                n += 1
                candidate_tags.append(self.tag(
                    'candidate',
                    *[self.tag(k, v) for k, v in ent.items()]
                ))
                if n <= MAX_CANDIDATE_TAGS:
                    break

            top = get_tree_top(candidate)
            inode = candidate.vp['inode'][top]
            match_tag = self.tag('match', self.tag('inode', inode), *candidate_tags)
            self._top.append(match_tag)

    def _make_source_tag(self, image_filename=None, mount_point=None):
        """Create the ``<source>`` tag and add it to the XML document.

        :param str image_filename: Path (absolute or relative) to the input
            file. Will be inserted into a ``<dfxml:image_filename>`` tag.
        :param str mount_point: Path where the image is mounted on the system.
        :rtype: None
        """
        if image_filename is None and mount_point is None:
            # No need to do anything if both are None
            return

        src_tag = self.tag('source')

        if image_filename is not None:
            src_tag.append(self.tag('dfxml:image_filename', image_filename))

        if mount_point is not None:
            src_tag.append(self.tag('mount_point', mount_point))

        self._top.append(src_tag)

    def _make_creator_tag(self):
        """Create the ``<creator>`` tag and add it to the XML document.

        The ``<creator>`` tag comes from DFXML and contains information about
        the program that created the XML file to help track provenance.

        :rtype: None
        """
        sysname, nodename, release, version, machine = os.uname()
        self._top.append(
            self.tag('dfxml:creator',
                     self.tag('dfxml:program', ''),  # TODO
                     self.tag('dfxml:version', ''),  # TODO
                     # self.tag('dfxml:build_environment',  # TODO
                     #          self.tag('dfxml:compiler', ),
                     #          self.tag('dfxml:compilation_date', ),
                     #          self.tag('dfxml:library', ),  # unbounded
                     #          ),
                     self.tag('dfxml:execution_environment',
                              self.tag('dfxml:os_sysname', sysname),
                              self.tag('dfxml:os_release', release),
                              self.tag('dfxml:os_version', version),
                              self.tag('dfxml:host', nodename),
                              self.tag('dfxml:arch', machine),
                              self.tag('dfxml:command_line', ' '.join(sys_argv)),
                              # self.tag('dfxml:uid', str(os.getuid())),
                              self.tag('dfxml:uid', os.getuid()),
                              self.tag('dfxml:username', os.getlogin()),
                              # self.tag('dfxml:start_time', ),  # TODO
                              ),
                     # self.tag('dfxml:library', ''),  # unbounded  # TODO
                     )
        )

    def tag(self, tag_name, *args):
        """Create a new tag and add everything from `args` as its contents.

        :param str tag_name: Name of the new tag.
        :param args: All parameters after `tag_name` will be appended to the
            contents of the new tag.
        :return: The new tag.
        :rtype: bs4.Tag
        """
        new_tag = self._soup.new_tag(tag_name)
        for x in args:
            try:
                new_tag.append(x)
            except AttributeError:
                new_tag.append(str(x))
        return new_tag


def calc_confidence(distance, fam_size, delta=3):
    return (e ** (-1 * delta * distance)) / fam_size
