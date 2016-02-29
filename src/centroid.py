import logging
from copy import deepcopy as copy
from datetime import datetime, timezone
from math import ceil, sqrt

import graph_tool.all as gt
from sqlalchemy import Table, select

from chrome_db import DB_META, USED_TO_DB

# USED_FIELDS = ('_c_ctime', '_c_num_child_dirs', '_c_num_child_files', '_c_mode', '_c_depth', '_c_type')
USED_FIELDS = ('_c_num_child_dirs', '_c_num_child_files', '_c_mode', '_c_depth', '_c_type')
ISO_TIME = '%Y-%m-%dT%H:%M:%SZ'

__all__ = ['calc_centroid', 'centroid_difference', 'get_normalizing_vector', 'InvalidCentroidError', 'InvalidTreeError',
           'ISO_TIME', 'USED_FIELDS']


class InvalidTreeError(Exception):
    """
    Indicates a certain required property of the tree has been violated, such
    as a node having two parents, a vertex property not being valid, etc.
    """
    pass


class InvalidCentroidError(Exception):
    """
    Indicates a centroid was improperly formed, having invalid values, the
    wrong number of dimensions, or some other issue. The number of dimensions
    must match the number of values in the USED_FIELDS global tuple plus one,
    the last of which represents the size.
    """
    pass


class CentroidCalc(object):
    """
    From a digraph (implemented using graph_tool.Graph), determine the tree's
    centroid with respect to the USED_FIELDS.

    A centroid in physics represents the geographical midpoint of a shape,
    which is equivalent to the center of mass if the object has uniform mass
    distribution in a uniform gravitational field.

    We borrow this concept to represent the attributes of a tree for uniquely
    identifying it with a simple vector. The elegance of this solution is it
    does not rely on uniquely identifying the vertices in the tree during the
    process.

    The typical approach for using this class would be to instantiate it with
    a copy of the graph (sub-tree) for which the centroid should be
    calculated, then call the do_calc() method. At that point, the centroid
    vector is available from the centroid class property. If you need a copy
    of the tree including all the centroid fields, the graph class property
    will give you what you're looking for.

    The tree used to instantiate CentroidCalc must already have the following
    vertex properties with the identified types:

    * *ctime* (str) Most recent metadata (inode) change time with the format
      as given in ISO_TIME
    * *mode* (str) The mode (permissions) for the vertex's file
    * *type* (vector<short>) The set of file types for the file

    The reason *type* has the type "vector<short>" is to handle duplicate
    inode entries in the file system when creating the original graph.
    *Please Note*: The code in this class is not written to handle multiple
    values for the *type* field, so any resolution of duplicate values must
    have already been performed. The _set_properties method simply takes the
    first value in the vector.
    """

    def __init__(self, sub_tree, block_size=4096):
        assert isinstance(sub_tree, gt.Graph)
        self.digr = sub_tree
        self.digr.gp['centroid'] = self.digr.new_graph_property('vector<float>')
        self.digr.vp['_c_size'] = self.digr.new_vertex_property('int')
        self.digr.vp['_c_ctime'] = self.digr.new_vertex_property('int')
        self.digr.vp['_c_num_child_dirs'] = self.digr.new_vertex_property('int')
        self.digr.vp['_c_num_child_files'] = self.digr.new_vertex_property('int')
        self.digr.vp['_c_mode'] = self.digr.new_vertex_property('int')
        self.digr.vp['_c_depth'] = self.digr.new_vertex_property('int')
        self.digr.vp['_c_type'] = self.digr.new_vertex_property('int')

        self.block_size = block_size
        self.top = get_tree_top(self.digr)
        self._cent_calculated = False
        logging.debug('Created CentroidCalc object with %d vertices.' % self.digr.num_vertices())

    def do_calc(self):
        """
        Calculate the centroid for the tree. After calling this method, the
        centroid vector is available from self.centroid.

        :return: None
        :rtype: None
        """
        self._set_properties(self.top, 0)

        sums = {'w': 0,  # Size (weight)
                't': 0,  # Creation time
                'u': 0,  # Child dirs
                'v': 0,  # Child files
                'x': 0,  # Permissions
                'y': 0,  # Depth
                'z': 0,  # File type
                }
        for _e in self.digr.edges():
            p, q = _e.source(), _e.target()
            pw = self.digr.vp['_c_size'][p]
            qw = self.digr.vp['_c_size'][q]
            sums['w'] += pw + qw

            for s, prop in zip(('t', 'u', 'v', 'x', 'y', 'z'), USED_FIELDS):
                sums[s] += pw * self.digr.vp[prop][p] + qw * self.digr.vp[prop][q]

        for s in ('t', 'u', 'v', 'x', 'y', 'z')[:len(USED_FIELDS)]:
            self.digr.gp['centroid'].append(sums[s]/sums['w'])
        # Add the size and ttl_files properties
        self.digr.gp['centroid'].append(sums['w'])
        self.digr.gp['centroid'].append(self.size)  # Corresponds to the number of files, or ttl_files
        self._cent_calculated = True

    def _set_properties(self, vertex, depth, baseline_time=None):
        """
        Using the existing internal properties of the tree, calculate and save
        the fields used to calculate the centroid, converting to the correct
        type where necessary.

        This function is recursive. As such, the first time it is called must
        be with the top-most vertex of the tree and depth of 0.

        :param vertex: The current vertex to work with, save properties for.
        :type vertex: graph_tool.Vertex
        :param depth: Distance from the top-most vertex.
        :type depth: int
        :param baseline_time: The inode changed time of the top-most vertex.
        :type baseline_time: int | None
        :return: None
        :rtype: None
        """
        # Convert this from str to int representing POSIX timestamp in UTC timezone
        ctime = self.digr.vp['ctime'][vertex]
        ctime = int(datetime.strptime(ctime, ISO_TIME).replace(tzinfo=timezone.utc).timestamp())

        if baseline_time is None:
            baseline_time = ctime

        # Calculate relative time difference
        self.digr.vp['_c_ctime'][vertex] = ctime - baseline_time

        num_child_dirs = 0
        num_child_files = 0

        for child in vertex.out_neighbours():
            # TODO: Make sure the heuristic for resolving multiple types has been written before this is used
            child_type = int(self.digr.vp['type'][child][0])
            if child_type == 2:
                num_child_dirs += 1
            else:
                num_child_files += 1

            self._set_properties(child, depth+1, baseline_time)

        # Child numbers
        self.digr.vp['_c_num_child_dirs'][vertex] = num_child_dirs
        self.digr.vp['_c_num_child_files'][vertex] = num_child_files

        # Size
        size = int(self.digr.vp['filesize'][vertex])  # Get original size first
        size = int(ceil(size / self.block_size))  # How many blocks does it occupy?
        self.digr.vp['_c_size'][vertex] = size

        # Permissions
        try:
            perms = int(self.digr.vp['mode'][vertex])
        except ValueError:
            logging.critical('Encountered a vertex with an invalid value for mode, couldn\'t convert to int: %s' %
                             self.digr.vp['mode'][vertex])
            raise InvalidTreeError('All vertices in the tree must have a valid mode value.')
        self.digr.vp['_c_mode'][vertex] = perms

        # Depth
        self.digr.vp['_c_depth'][vertex] = depth

        # Type
        self.digr.vp['_c_type'][vertex] = int(self.digr.vp['type'][vertex][0])

    @property
    def centroid(self):
        if not self._cent_calculated:
            self.do_calc()
        return tuple(self.digr.gp['centroid'])

    @property
    def graph(self):
        return self.digr.copy()

    @property
    def size(self):
        return self.digr.num_vertices()


def get_tree_top(digr):
    """
    Traverse the subtree at digr and return the top-most vertex.

    :param digr: Some graph object.
    :type digr: graph_tool.Graph
    :return: The top-most vertex in the graph.
    :rtype: graph_tool.Vertex
    """
    _v = None
    for _v in digr.vertices():
        break

    # Validate the starting vertex
    if _v is None:
        logging.critical('Tree has no vertices, cannot calculate centroid.')
        raise InvalidTreeError('Given subtree has no vertices.')

    # Find the top-most vertex
    while True:
        # Each vertex should have exactly 1 incoming edge
        if _v.in_degree() > 1:
            logging.critical('Graph is not a valid tree, found vertex with >1 parent.')
            raise InvalidTreeError('Given subtree has vertices with >1 parent.')

        elif _v.in_degree() == 0:
            # If a vertex has no incoming edges, it must be the top
            return _v

        else:
            _v = list(_v.in_neighbours())[0]


def calc_centroid(sub_tree):
    """
    Convenience function for calculating the centroid for a tree.

    :param sub_tree: The tree for which the centroid should be calculated.
    :type sub_tree: graph_tool.Graph
    :return: The centroid vector, as a tuple. Has the same number of
             dimensions as the length of USED_FIELDS + 1.
    :rtype: tuple
    """
    assert isinstance(sub_tree, gt.Graph)
    calc = CentroidCalc(sub_tree)
    calc.do_calc()
    cent = copy(calc.centroid)
    # Try to conserve memory usage
    del calc
    return cent


def centroid_difference(centroid1, centroid2, normalize=None):
    """
    Return the magnitude of the difference of the two centroid vectors, both
    of which must have the same length as USED_FIELDS + 1.

    To normalize the values in the centroids before calculating their
    difference, pass a tuple as normalize with the same length.

    :param centroid1: A centroid.
    :type centroid1: tuple
    :param centroid2: A centroid.
    :type centroid2: tuple
    :param normalize: Set of normalizing values.
    :type normalize: tuple|list
    :return: The magnitude of the vector difference.
    :rtype: float
    """
    l1 = len(centroid1)
    l2 = len(centroid2)
    lu = len(USED_FIELDS) + 2
    if l1 != l2 or l1 != lu:
        logging.critical('Cannot calculate centroid difference for vectors with invalid lengths. (%d and %d, should be '
                         '%d)' % (l1, l2, lu))
        print(centroid1)
        print(centroid2)
        raise InvalidCentroidError('Both centroid vectors must have length %d' % lu)
    if normalize is not None and len(normalize) != lu:
        logging.critical('Cannot calculate centroid difference using a normalizing vectors with an invalid length.')
        raise InvalidCentroidError('Normalizing centroid vector must have length %d' % lu)

    diff = []

    # Non-normalized difference
    if normalize is None:
        normalize = [1] * lu

    # Make sure the ttl_files field of the normalizing vector is 1
    if normalize[-1] != 1:
        normalize = normalize[:-1] + (1,)

    for i, j, n in zip(centroid1, centroid2, normalize):
        diff.append((i / n) - (j / n))

    magnitude = 0
    for k in diff:
        magnitude += k**2
    return sqrt(magnitude)


def get_normalizing_vector(db_meta=DB_META):
    """
    Return the normalizing vector for centroids in the database.

    :param db_meta: The meta object to access the DB.
    :type db_meta: sqlalchemy.MetaData
    :return: The current normalizing vector for the DB.
    :rtype: tuple
    """
    db_conn = db_meta.bind.connect()
    extension = Table('extension', db_meta)

    all_fields = USED_FIELDS + ('_c_size',)
    norm_dict = dict.fromkeys(all_fields, float('-inf'))
    norm_tup = tuple()

    for row in db_conn.execute(select([extension])):
        for field in all_fields:
            col = getattr(extension.c, USED_TO_DB[field])
            if row[col] > norm_dict[field]:
                norm_dict[field] = row[col]
    for field in all_fields:
        norm_tup += (norm_dict[field],)

    db_conn.close()
    return norm_tup + (1,)
