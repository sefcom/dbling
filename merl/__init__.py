#!/usr/bin/env python3
# *-* coding: utf-8 *-*
import logging
from math import e
from operator import itemgetter

from bs4 import BeautifulSoup
from sqlalchemy import Table, select

from common.centroid import CentroidCalc, get_normalizing_vector, centroid_difference, USED_FIELDS, USED_TO_DB, DB_META


STARTER = '<merl xmlns:df="https://github.com/dfxml-working-group/dfxml_schema"></merl>'
MAX_FAMILY_MATCHES = 1000


class Merl:
    def __init__(self):
        self._soup = BeautifulSoup(STARTER, 'xml')
        self._top = self._soup.merl
        self._source_recorded = False

        self._db_conn = DB_META.bind.connect()
        self._extension = Table('extension', DB_META)
        self._cent_fam = Table('centroid_family', DB_META)
        self._norm_vec = get_normalizing_vector()

        self._cent_cols = [getattr(self._cent_fam.c, USED_TO_DB[x]) for x in (USED_FIELDS + ('_c_size',))] + \
                          [self._cent_fam.c.ttl_files]
        self._centroid_select_fields = self._cent_cols + [self._cent_fam.c.pk]
        self._out_file = None

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

    def close_db(self):
        self._db_conn.close()

    def match_candidates(self, candidates_list):
        n = 0
        for c in candidates_list:
            n += 1
            self.match_candidate(c, n)

    def match_candidate(self, candidate, match_num=None):
        # TODO: Add DFXML source file information from the original graph
        if not self._source_recorded:
            self._get_source(candidate)

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

            # If the distance is less than the max stored hits, add it, remove the one it bested
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

            s_hits = select([self._extension.c.ext_id, self._extension.c.version]).\
                where(self._extension.c.centroid_group == h)
            for ext in self._db_conn.execute(s_hits):
                # TODO: Complete this entry information
                # To do that, we need to parse the manifest files for all the extensions and add the extension name and
                # vendor to the database.
                entry = dict(ext_id=ext[self._extension.c.ext_id],
                             ext_ver=ext[self._extension.c.version],
                             # ext_name='Name unavailable',  # ext[self._extension.c.],
                             # ext_vendor='Vendor unavailable',  # ext[self._extension.c.],
                             confidence=conf)
                hit_entries.append(entry)

        _n = ''
        if match_num is not None:
            _n = ' (%d)' % match_num
        logging.debug(('Calculated the matches for a candidate graph with %d vertices.' % cent.size) + _n)

        # Add the fields to the MERL file  # TODO
        if match_num is not None:
            print('\nC%d Candidate Matches' % match_num, file=self._out_file)
            print('---------------------\n', file=self._out_file)
        else:
            print('\nCandidate Matches', file=self._out_file)
            print('-----------------\n', file=self._out_file)
        n = 0
        for ent in sorted(hit_entries, key=itemgetter('confidence'), reverse=True):
            n += 1
            print('#%d' % n, file=self._out_file)
            for k in ent:
                print('%s: %s' % (k, ent[k]), file=self._out_file)
            print(file=self._out_file)

    def _get_source(self, graph):
        # TODO:
        self._source_recorded = True


def calc_confidence(distance, fam_size, delta=3):
    return (e ** (-1 * delta * distance)) / fam_size
