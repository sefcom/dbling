
from copy import deepcopy as copy
from datetime import datetime, timezone
import graph_tool.all as gt
import logging
from math import ceil, sqrt


USED_FIELDS = ('_c_ctime', '_c_num_child_dirs', '_c_num_child_files', '_c_mode', '_c_depth', '_c_type')
ISO_TIME = '%Y-%m-%dT%H:%M:%SZ'

__all__ = ['calc_centroid', 'centroid_difference', 'InvalidCentroidError', 'InvalidTreeError', 'ISO_TIME',
           'USED_FIELDS']


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
        self.top = self._get_tree_top()
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
        # Add the size property
        self.digr.gp['centroid'].append(sums['w'])

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
        size = int(self.digr.vp['size'][vertex])  # Get original size first
        size = int(ceil(size / self.block_size))  # How many blocks does it occupy?
        self.digr.vp['_c_size'][vertex] = size

        # Permissions
        try:
            perms = int(self.digr.vp['mode'][vertex])
        except ValueError:
            logging.critical('Encountered a vertex with an invalid value for mode, couldn\'t convert to int.')
            raise InvalidTreeError('All vertices in the tree must have a valid mode value.')
        self.digr.vp['_c_mode'][vertex] = perms

        # Depth
        self.digr.vp['_c_depth'][vertex] = depth

        # Type
        self.digr.vp['_c_type'][vertex] = int(self.digr.vp['type'][vertex][0])

    def _get_tree_top(self):
        """
        Traverse the self.digr subtree and return the top-most vertex.

        :return: The top-most vertex in the graph.
        :rtype: graph_tool.Vertex
        """
        _v = None
        for _v in self.digr.vertices():
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

    @property
    def centroid(self):
        return tuple(self.digr.gp['centroid'])

    @property
    def graph(self):
        return self.digr.copy()


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


def centroid_difference(centroid1, centroid2):
    """
    Return the magnitude of the difference of the two centroid vectors, both
    of which must have the same length as USED_FIELDS + 1.

    :param centroid1: A centroid.
    :type centroid1: tuple
    :param centroid2: A centroid.
    :type centroid2: tuple
    :return: The magnitude of the vector difference.
    :rtype: float
    """
    if len(centroid1) != len(centroid2) or len(centroid1) != (len(USED_FIELDS) + 1):
        logging.critical('Cannot calculate centroid difference for vectors with invalid lengths.')
        raise InvalidCentroidError('Both centroid vectors must have length %d' % (len(USED_FIELDS) + 1))

    diff = []
    for i, j in zip(centroid1, centroid2):
        diff.append(i-j)

    magnitude = 0
    for k in diff:
        magnitude += k**2
    return sqrt(magnitude)
