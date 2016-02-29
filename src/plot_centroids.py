#!/usr/bin/env python3
"""
Usage: plot_centroids.py [FUNCTION]

FUNCTION can be one of: diff1, hist, (more coming soon)
"""

import json

import plotly.plotly as py
from docopt import docopt
from plotly.graph_objs import Scatter, Marker, Data, Histogram
from sqlalchemy import select, Table

from centroid import centroid_difference, get_normalizing_vector, USED_FIELDS, USED_TO_DB, DB_META


class Plotter:

    def __init__(self):
        # Initialize database
        with open('crx_conf.json') as fin:
            db_conf = json.load(fin)['db']

        self.db_meta = DB_META
        self.db_conn = self.db_meta.bind.connect()
        self.extension = Table('extension', self.db_meta)
        self.all_fields = USED_FIELDS + ('_c_size',)

        # Get normalizing values
        self.norm_tup = get_normalizing_vector(self.db_meta)

        self.quit = lambda: None
        self.q = lambda: None

    def diff1(self):
        point_data = {}  # Keys: distances, Values: list of extension IDs
        baseline_row = None
        baseline_id = None

        # Iterate through the rows
        for row in self.db_conn.execute(select([self.extension])):
            # Get the centroid
            centroid = ()
            for field in self.all_fields:
                col = getattr(self.extension.c, USED_TO_DB[field])
                centroid += (row[col],)

            if baseline_row is None:
                baseline_row = centroid
                baseline_id = row[self.extension.c.ext_id]
                continue

            diff = centroid_difference(baseline_row, centroid, self.norm_tup)
            try:
                point_data[diff].append(row[self.extension.c.ext_id])
            except KeyError:
                point_data[diff] = [row[self.extension.c.ext_id]]

        diffs = list(point_data.keys())
        diffs.sort()
        y = []
        text = []
        for r in diffs:
            for p in point_data[r]:
                y.append(r)
                text.append(p)

        trace = Scatter(
            y=y[:40000],
            text=text[:40000],
            name='Diff against %s' % baseline_id,
            mode='markers',
            marker=Marker(size=3)
        )

        data = Data([trace])
        plot_url = py.plot(data, filename="centroid-distances-normalized")
        print("Plot ready at: %s" % plot_url)

    def hist(self):
        ids_calculated = []
        centroid_counts = []
        key_field = USED_TO_DB[self.all_fields[0]]

        # Iterate through the rows
        for row in self.db_conn.execute(select([self.extension])):
            # Skip if we've already seen this row
            if row[self.extension.c.ext_id] in ids_calculated:
                continue
            ids_calculated.append(row[self.extension.c.ext_id])
            same_centroid = 1

            # Get the centroid
            centroid = ()
            for field in self.all_fields:
                col = getattr(self.extension.c, USED_TO_DB[field])
                centroid += (row[col],)

            # Do some really inefficient coding...
            result = self.db_conn.execute(select([self.extension]).
                                          where((getattr(self.extension.c, key_field)) == row[key_field]))
            for other_row in result:
                # Get the other centroid
                other_centroid = ()
                for field in self.all_fields:
                    col = getattr(self.extension.c, USED_TO_DB[field])
                    other_centroid += (other_row[col],)

                # Calculate the difference between the two vectors
                diff = centroid_difference(centroid, other_centroid, self.norm_tup)
                if diff == 0:
                    same_centroid += 1
                    ids_calculated.append(other_row[self.extension.c.ext_id])
            centroid_counts.append(same_centroid)

        # Create the histogram
        data = Data([Histogram(x=centroid_counts)])
        plot_url = py.plot(data, filename="centroid-cluster-histogram")
        print("Plot ready at: %s" % plot_url)


if __name__ == '__main__':
    args = docopt(__doc__)

    plot = Plotter()
    try:
        getattr(plot, args['FUNCTION'])()
    except AttributeError:
        while True:
            try:
                _resp = input("What function do you want to call: ")
                getattr(plot, _resp)()
            except AttributeError:
                print("\nUnknown function. Try again. 'quit' or 'q' to exit.")
                pass
            except KeyboardInterrupt:
                # TODO: Deinit on plot object
                break
            else:
                break
