#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import stat
from datetime import datetime, date, timedelta
from hashlib import sha256
from os import path

import graph_tool.all as gt

from centroid import ISO_TIME
from clr import add_color_log_levels
from const import EVAL_NONE, IN_PAT_VAULT, ENC_PAT, MIN_DEPTH

__all__ = ['FILE_TYPES', 'TYPE_TO_NAME', 'SLICE_PAT', 'CRX_URL', 'validate_crx_id', 'MalformedExtId',
           'add_color_log_levels', 'get_dir_depth', 'make_graph_from_dir', 'get_crx_version', 'init_graph',
           'calc_chrome_version', 'get_id_version']

FILE_TYPES = {stat.S_IFREG: 1,
              stat.S_IFDIR: 2,
              stat.S_IFCHR: 3,
              stat.S_IFBLK: 4,
              stat.S_IFIFO: 5,
              stat.S_IFSOCK: 6,
              stat.S_IFLNK: 7}
TYPE_TO_NAME = {1: 'r',
                2: 'd',
                3: 'c',  # TODO: 3-7 may not actually correspond to the DFXML standard
                4: 'b',
                5: 'f',
                6: 's',
                7: 'l'}


SLICE_PAT = re.compile('.*(/home.*)')
CRX_URL = 'https://chrome.google.com/webstore/detail/%s'


def validate_crx_id(crx_id):
    """
    Check that the Chrome extension ID has three important properties:

    1. It must be a string
    2. It must have alpha characters only (strictly speaking, these should be
       lowercase and only from a-p, but checking for this is a little
       overboard)
    3. It must be 32 characters long

    :param crx_id:
    :return:
    """
    try:
        assert isinstance(crx_id, str)
        assert crx_id.isalnum()
        assert len(crx_id) == 32
    except AssertionError:
        raise MalformedExtId


class MalformedExtId(Exception):
    """Raised when an ID doesn't have the correct form."""


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


def make_graph_from_dir(top_dir, digr=None):
    """
    Given a directory path, create and return a directed graph representing it
    and all its contents.

    :param top_dir: Path to the top-most directory to add to the graph.
    :type top_dir: str
    :param digr: If given, start with a previously created graph.
    :type digr: graph_tool.all.Graph
    :return: The graph object with all the information about the directory.
    :rtype: graph_tool.all.Graph
    """
    assert path.isdir(top_dir)
    # TODO: dd? DFXML? Or is that overkill?

    # Initialize the graph with all the vertex properties, then add the top directory vertex
    slice_path = True  # TODO: Not working
    if digr is None or not isinstance(digr, gt.Graph):
        digr = init_graph()
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


def get_crx_version(crx_path):
    """
    From the path to a CRX, extract and return the version number as a string.

    The return value from the download() function is in the form:
    <extension ID>_<version>.crx

    The <version> part of that format is "x_y_z" for version "x.y.z". To
    convert to the latter, we need to 1) get the basename of the path, 2) take
    off the trailing ".crx", 3) remove the extension ID and '_' after it, and
    4) replace all occurrences of '_' with '.'.

    :param crx_path: The full path to the downloaded CRX, as returned by the
                     download() function.
    :type crx_path: str
    :return: The version number in the form "x.y.z".
    :rtype: str
    """
    # TODO: This approach has some issues with catching some outliers that don't match the regular pattern
    ver_str = path.basename(crx_path).split('.crx')[0].split('_', 1)[1]
    return ver_str.replace('_', '.')


def get_id_version(crx_path):
    """
    From the path to a CRX, extract and return the ID and version as a string.

    :param crx_path: The full path to the downloaded CRX.
    :type crx_path: str
    :return: The ID and version number as a tuple: (id, num)
    :rtype: tuple
    """
    crx_id, ver_str = path.basename(crx_path).split('.crx')[0].split('_', 1)
    ver_str = ver_str.replace('_', '.')
    return crx_id, ver_str


def set_vertex_props(digraph, vertex, filename, slice_path=False):
    """
    Use Python's os.stat method to store information about the file in the
    vertex properties of the graph the vertex belongs to. Return the SHA256
    hash of the file's full, normalized path.

    :param digraph: The graph the vertex belongs to.
    :type digraph: graph_tool.all.Graph
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


def init_graph():
    """
    Create a new graph and give it the vertex properties needed later.

    :return: The graph object.
    :rtype: graph_tool.all.Graph
    """
    gr = gt.Graph()
    # Create the internal property maps
    # TODO: Clean this up when the fields are finalized
    gr.vp['inode'] = gr.new_vertex_property('int')
    gr.vp['parent_inode'] = gr.new_vertex_property('int')
    gr.vp['filename'] = gr.new_vertex_property('string')
    gr.vp['filename_id'] = gr.new_vertex_property('string')
    gr.vp['filename_end'] = gr.new_vertex_property('string')
    gr.vp['name_type'] = gr.new_vertex_property('string')
    gr.vp['type'] = gr.new_vertex_property('vector<short>')
    # gr.vp['alloc'] = gr.new_vertex_property('bool')
    # gr.vp['used'] = gr.new_vertex_property('bool')
    # gr.vp['fs_offset'] = gr.new_vertex_property('string')
    gr.vp['filesize'] = gr.new_vertex_property('string')
    # gr.vp['src_files'] = gr.new_vertex_property('vector<short>')
    gr.vp['encrypted'] = gr.new_vertex_property('bool')
    gr.vp['eval'] = gr.new_vertex_property('bool')
    gr.vp['size'] = gr.new_vertex_property('string')
    gr.vp['mode'] = gr.new_vertex_property('string')
    gr.vp['uid'] = gr.new_vertex_property('string')
    gr.vp['gid'] = gr.new_vertex_property('string')
    gr.vp['nlink'] = gr.new_vertex_property('string')
    gr.vp['mtime'] = gr.new_vertex_property('string')
    gr.vp['ctime'] = gr.new_vertex_property('string')
    gr.vp['atime'] = gr.new_vertex_property('string')
    # gr.vp['crtime'] = gr.new_vertex_property('string')
    # gr.vp['color'] = gr.new_vertex_property('vector<float>')
    # gr.vp['shape'] = gr.new_vertex_property('string')
    gr.vp['dir_depth'] = gr.new_vertex_property('short')
    gr.vp['gt_min_depth'] = gr.new_vertex_property('bool')
    return gr


def separate_mode_type(mode):
    """
    Separate out the values for the mode (permissions) and the file type from
    the given mode.

    Both returned values are integers. The mode is just the permissions
    (usually displayed in the octal format), and the type corresponds to the
    standard VFS types:

    * 0: Unknown file
    * 1: Regular file
    * 2: Directory
    * 3: Character device
    * 4: Block device
    * 5: Named pipe (identified by the Python stat library as a FIFO)
    * 6: Socket
    * 7: Symbolic link

    :param mode: The mode value to be separated.
    :type mode: int
    :return: Tuple of ints in the form: (mode, type)
    :rtype: tuple
    """
    m = stat.S_IMODE(mode)
    t = stat.S_IFMT(mode)
    return m, FILE_TYPES.get(t, 0)


def calc_chrome_version(last_version, release_date, release_period=10):
    """
    Calculate the most likely version number of Chrome is based on the last
    known version number and its release date, based on the number of weeks
    (release_period) it usually takes to release the next major version. A
    list of releases and their dates is available at
    https://en.wikipedia.org/wiki/Google_Chrome_release_history.

    :param last_version: Last known version number, e.g. "43.0". Should only
                         have the major and minor version numbers and exclude
                         the build and patch numbers.
    :type last_version: str
    :param release_date: Release date of the last known version number. Must
                         be a list of three integers: [YYYY, MM, DD].
    :type release_date: list
    :param release_period: Typical number of weeks between releases.
    :type release_period: int
    :return: The most likely current version number of Chrome in the same
             format required of the last_version parameter.
    :rtype: str
    """
    base_date = date(release_date[0], release_date[1], release_date[2])
    today = date.today()
    td = int((today - base_date) / timedelta(weeks=release_period))
    return str(float(last_version) + td)
