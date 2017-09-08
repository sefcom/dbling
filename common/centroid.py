import logging
from copy import deepcopy as copy
from datetime import datetime, timezone
from math import ceil, sqrt

from sqlalchemy import Table, select

from common.chrome_db import DB_META
from common.const import *
from common.graph import DblingGraph

__all__ = ['calc_centroid', 'centroid_difference', 'get_normalizing_vector', 'InvalidCentroidError', 'InvalidTreeError',
           'ISO_TIME', 'USED_FIELDS']


class InvalidTreeError(Exception):
    """
    Indicates a certain required property of the tree has been violated, such
    as a node having two parents, a vertex property not being valid, etc.
    """


class InvalidCentroidError(Exception):
    """
    Indicates a centroid was improperly formed, having invalid values, the
    wrong number of dimensions, or some other issue. The number of dimensions
    must match the number of values in the USED_FIELDS global tuple plus one,
    the last of which represents the size.
    """


class CentroidCalc:
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

    def __init__(self, sub_tree, *, block_size=4096):
        """An object to keep track of calculating a centroid for an extension.

        :param DblingGraph sub_tree: The graph object to use to calculate the
            centroid. In addition to the graph property ``has_encrypted_files``,
            ``sub_tree`` must already have the following vertex properties
            populated:

            - ``type``
            - ``filesize``
            - ``ctime``
            - ``filename_b_len``
            - ``mode``
        :param int block_size: Block size that eCryptfs uses. Should always be
            4096, but I thought I'd add it as an option just in case.
        """
        assert isinstance(sub_tree, DblingGraph)
        self.digr = sub_tree
        self.digr.gp['centroid'] = self.digr.new_graph_property('vector<float>')
        self.digr.vp['_c_size'] = self.digr.new_vertex_property('int')
        # self.digr.vp['_c_ctime'] = self.digr.new_vertex_property('int')  # Removed because it wasn't helping things
        self.digr.vp['_c_num_child_dirs'] = self.digr.new_vertex_property('int')
        self.digr.vp['_c_num_child_files'] = self.digr.new_vertex_property('int')
        self.digr.vp['_c_mode'] = self.digr.new_vertex_property('int')
        self.digr.vp['_c_depth'] = self.digr.new_vertex_property('int')
        self.digr.vp['_c_type'] = self.digr.new_vertex_property('int')

        # Making the (safe) assumption that if *any* files in the graph were encrypted, all of the files that are left
        # must be encrypted.
        self._has_crypt = self.digr.gp['has_encrypted_files']

        self.block_size = block_size
        self.top = get_tree_top(self.digr)
        self._cent_calculated = False
        # logging.debug('Created CentroidCalc object with %d vertices.' % self.digr.num_vertices())

    def do_calc(self):
        """Calculate the centroid for the tree.

        After calling this method, the centroid vector is available from the
        :attr:`~CentroidCalc.centroid` property.

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
        # self.digr.vp['_c_ctime'][vertex] = ctime - baseline_time

        num_child_dirs = 0
        num_child_files = 0

        child_name_lens = []

        for child in vertex.out_neighbours():
            # TODO: Make sure the heuristic for resolving multiple types has been written before this is used
            child_type = int(self.digr.vp['type'][child][0])
            if child_type == 2:
                num_child_dirs += 1
            else:
                num_child_files += 1

            child_name_lens.append(int(self.digr.vp['filename_b_len'][child]))

            self._set_properties(child, depth+1, baseline_time)

        # Child numbers
        self.digr.vp['_c_num_child_dirs'][vertex] = num_child_dirs
        self.digr.vp['_c_num_child_files'][vertex] = num_child_files

        # Size
        self.digr.vp['_c_size'][vertex] = self._blocks_used(size=int(self.digr.vp['filesize'][vertex]),
                                                            f_type=int(self.digr.vp['type'][vertex][0]),
                                                            child_name_lens=child_name_lens,
                                                            )

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
        """The centroid vector.

        :rtype: tuple
        """
        if not self._cent_calculated:
            self.do_calc()
        return tuple(self.digr.gp['centroid'])

    @property
    def graph(self):
        """Return a copy of the graph object.

        :rtype: DblingGraph
        """
        return self.digr.copy()

    @property
    def size(self):
        """Return the number of vertices in the graph.

        :rtype: int
        """
        return self.digr.num_vertices()

    def _blocks_used(self, size, f_type, child_name_lens):
        """Calculate the size of a file/dir on disk using its metadata.

        :param int size: The original size of the file.
        :param int f_type: File type number (Unix-style). The value of this
            parameter will be compared against the :class:`FType` enum type.
        :param list child_name_lens: List of the lengths of all the files in a
            directory *in bytes*. If the current file is not a directory, the
            list should be empty, but no error will occur if it isn't.
        :return: Number of blocks occupied by the file.
        :rtype: int
        """
        size = int(size)
        f_type = int(f_type)

        if self._has_crypt:
            # If we're working with encrypted files, we don't need to do all the fancy calculations below. Those are
            # for *predicting* the size after encryption. If it's already encrypted, we don't need to predict.
            return int(ceil(size / self.block_size))

        if f_type == FType.dir:
            size2 = 0
            for n in child_name_lens:
                size2 += dir_entry_size(n)
            # If size2 isn't bigger than size, something went wrong
            if size > size2:
                logging.debug('Predicted lower size of a directory was not bigger than the upper size')
            else:
                size = size2

        elif type == FType.reg:
            # eCryptfs adds an 8kb header to regular files
            size += ECRYPTFS_FILE_HEADER_BYTES

        # Now that we have an accurate size, calculate how many blocks it occupies
        return int(ceil(size / self.block_size))


def dir_entry_size(filename_length, is_encrypted=False):
    """Calculate the number of bytes a file occupies in a directory file.

    :param int filename_length: Length of the file's name *in bytes*.
    :param bool is_encrypted: Whether the filename is already encrypted.
    :return: Number of bytes the file occupies in a directory file. This
        includes any padding bytes to make the filename a multiple of four, as
        well as the bytes taken by other fields in the directory entry.
    :rtype: int
    """
    if not is_encrypted:
        # Figure out what the encrypted length would be
        filename_length = ECRYPTFS_SIZE_THRESHOLDS[filename_length >> 4]

    # Make sure the filename length is a multiple of 4
    if filename_length % 4:
        filename_length += 4 - (filename_length % 4)

    # Add the size of the directory entry fields and return
    return DENTRY_FIELD_BYTES + filename_length


def get_tree_top(digr):
    """Traverse the subtree at digr and return the top-most vertex.

    :param digr: Some graph object.
    :type digr: common.graph.DblingGraph
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
    """Convenience function for calculating the centroid for a tree.

    :param sub_tree: The tree for which the centroid should be calculated.
    :type sub_tree: common.graph.DblingGraph
    :return: The centroid vector, as a tuple. Has the same number of
             dimensions as the length of USED_FIELDS + 1.
    :rtype: tuple
    """
    assert isinstance(sub_tree, DblingGraph)
    return copy(CentroidCalc(sub_tree).centroid)


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
            if row[col] is not None and row[col] > norm_dict[field]:
                norm_dict[field] = row[col]
    for field in all_fields:
        norm_tup += (norm_dict[field],)

    db_conn.close()
    return norm_tup + (1,)
