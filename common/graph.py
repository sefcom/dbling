# *-* coding: utf-8 *-*

import os
import re
from datetime import datetime
from hashlib import sha256
from os import path

import graph_tool.all as gt
from graph_tool.all import graph_draw  # Import this so others have access to it

from common.const import EVAL_NONE, IN_PAT_VAULT, ENC_PAT, MIN_DEPTH, SLICE_PAT, ISO_TIME, TYPE_TO_NAME
from common.util import separate_mode_type


class DblingGraph(gt.Graph):

    def __init__(self, extended_attrs=False):
        super().__init__()

        # Create the internal property maps
        # TODO: Clean this up when the fields are finalized
        self.vp['inode'] = self.new_vertex_property('int')
        self.vp['parent_inode'] = self.new_vertex_property('int')
        self.vp['filename'] = self.new_vertex_property('string')
        self.vp['filename_id'] = self.new_vertex_property('string')
        self.vp['filename_end'] = self.new_vertex_property('string')
        self.vp['filename_b_len'] = self.new_vertex_property('int')  # Length in bytes, as opposed to characters
        self.vp['name_type'] = self.new_vertex_property('string')
        self.vp['type'] = self.new_vertex_property('vector<short>')
        self.vp['filesize'] = self.new_vertex_property('string')
        self.vp['encrypted'] = self.new_vertex_property('bool')
        self.vp['eval'] = self.new_vertex_property('bool')
        self.vp['size'] = self.new_vertex_property('string')
        self.vp['mode'] = self.new_vertex_property('string')
        self.vp['uid'] = self.new_vertex_property('string')
        self.vp['gid'] = self.new_vertex_property('string')
        self.vp['nlink'] = self.new_vertex_property('string')
        self.vp['mtime'] = self.new_vertex_property('string')
        self.vp['ctime'] = self.new_vertex_property('string')
        self.vp['atime'] = self.new_vertex_property('string')
        self.vp['dir_depth'] = self.new_vertex_property('short')
        self.vp['gt_min_depth'] = self.new_vertex_property('bool')
        self.vp['keeper'] = self.new_vertex_property('bool', val=True)

        self.has_extended_attrs = False
        if extended_attrs:
            self.init_extended_attrs()

    def init_extended_attrs(self):
        if not self.has_extended_attrs:  # Only do this once
            self.vp['alloc'] = self.new_vertex_property('bool')
            self.vp['used'] = self.new_vertex_property('bool')
            self.vp['fs_offset'] = self.new_vertex_property('string')
            self.vp['src_files'] = self.new_vertex_property('vector<short>')
            self.vp['crtime'] = self.new_vertex_property('string')
            self.vp['color'] = self.new_vertex_property('vector<float>')
            self.vp['shape'] = self.new_vertex_property('string')

            self.has_extended_attrs = True

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    def load(self, *args, **kwargs):
        super().save(*args, **kwargs)


def make_graph_from_dir(top_dir, digr=None):
    """
    Given a directory path, create and return a directed graph representing it
    and all its contents.

    :param top_dir: Path to the top-most directory to add to the graph.
    :type top_dir: str
    :param digr: If given, start with a previously created graph.
    :type digr: DblingGraph
    :return: The graph object with all the information about the directory.
    :rtype: DblingGraph
    """
    assert path.isdir(top_dir)
    # TODO: dd? DFXML? Or is that overkill?

    # Initialize the graph with all the vertex properties, then add the top directory vertex
    slice_path = True  # TODO: Not working
    if digr is None or not isinstance(digr, DblingGraph):
        digr = DblingGraph()
        slice_path = False
    dir_v = digr.add_vertex()
    _id = set_vertex_props(digr, dir_v, top_dir, slice_path)
    id_to_vertex = {_id: dir_v}

    ttl_objects = 1

    for dirpath, dirnames, filenames in os.walk(top_dir):
        dir_id = sha256(path.abspath(dirpath).encode('utf-8')).hexdigest()

        for f in dirnames + filenames:
            full_filename = path.join(dirpath, f)
            vertex = digr.add_vertex()
            digr.add_edge(id_to_vertex[dir_id], vertex)
            vertex_id = set_vertex_props(digr, vertex, full_filename, slice_path)
            id_to_vertex[vertex_id] = vertex
            ttl_objects += 1

    # logging.info('Total imported file objects: %d' % ttl_objects)
    return digr


def set_vertex_props(digraph, vertex, filename, slice_path=False):
    """
    Use Python's os.stat method to store information about the file in the
    vertex properties of the graph the vertex belongs to. Return the SHA256
    hash of the file's full, normalized path.

    :param digraph: The graph the vertex belongs to.
    :type digraph: common.graph.DblingGraph
    :param vertex: The vertex object that will correspond with the file.
    :type vertex: graph_tool.all.Vertex
    :param filename: The path to the file.
    :type filename: str
    :param slice_path: When set, filename will be run through the SLICE_PAT
        before determining its depth. Can't remember what the advantage of
        this is though...
    :type slice_path: bool
    :return: SHA256 hash of the file's full, normalized path. (hex digest)
    :rtype: str
    """
    # Get the full, normalized path for the filename, then get its stat() info
    filename = path.abspath(filename)
    st = os.stat(filename, follow_symlinks=False)

    # Set all the attributes for the top directory vertex
    filename_id = sha256(filename.encode('utf-8')).hexdigest()
    m, t = separate_mode_type(st.st_mode)

    sliced_fn = filename
    if slice_path:
        _m = re.search(SLICE_PAT, filename)
        if _m:
            sliced_fn = _m.group(1)
    dir_depth = get_dir_depth(sliced_fn)

    try:
        parent_ver = list(vertex.in_neighbours())[0]
    except IndexError:
        pass
    else:
        digraph.vp['parent_inode'][vertex] = digraph.vp['inode'][parent_ver]

    digraph.vp['inode'][vertex] = st.st_ino
    digraph.vp['filename'][vertex] = filename
    digraph.vp['filename_id'][vertex] = filename_id
    digraph.vp['filename_end'][vertex] = path.basename(filename[-13:])
    digraph.vp['name_type'][vertex] = TYPE_TO_NAME[t]
    digraph.vp['type'][vertex] = (t,)
    digraph.vp['filesize'][vertex] = str(st.st_size)
    digraph.vp['size'][vertex] = str(st.st_size)
    digraph.vp['encrypted'][vertex] = bool(re.search(ENC_PAT, sliced_fn))
    digraph.vp['eval'][vertex] = EVAL_NONE
    digraph.vp['dir_depth'][vertex] = dir_depth
    digraph.vp['gt_min_depth'][vertex] = bool(re.match(IN_PAT_VAULT, sliced_fn)) and dir_depth >= MIN_DEPTH
    digraph.vp['mode'][vertex] = str(m)
    digraph.vp['uid'][vertex] = st.st_uid
    digraph.vp['gid'][vertex] = st.st_gid
    digraph.vp['nlink'][vertex] = st.st_nlink
    digraph.vp['mtime'][vertex] = datetime.fromtimestamp(st.st_mtime).strftime(ISO_TIME)
    digraph.vp['ctime'][vertex] = datetime.fromtimestamp(st.st_ctime).strftime(ISO_TIME)
    digraph.vp['atime'][vertex] = datetime.fromtimestamp(st.st_atime).strftime(ISO_TIME)
    return filename_id


def get_dir_depth(filename, slice_path=False):
    """
    Calculate how many directories deep the filename is.

    :param filename: The path to be split and counted.
    :type filename: str
    :param slice_path: When set, filename will be run through the SLICE_PAT
        before determining its depth. Can't remember what the advantage of
        this is though...
    :type slice_path: bool
    :return: The number of directory levels in the filename.
    :rtype: int
    """
    if slice_path:
        m = re.search(SLICE_PAT, filename)
        if m:
            filename = m.group(1)
    dir_depth = 0
    _head = filename
    while True:
        prev_head = _head
        _head, _tail = path.split(_head)
        if prev_head == _head:
            break
        if len(_tail) == 0:
            continue
        dir_depth += 1
        if len(_head) == 0:
            break
    return dir_depth
