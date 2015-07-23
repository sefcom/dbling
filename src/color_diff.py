#!/usr/bin/env python3
"""
Usage: color_diff.py [options]

Options:
 -f FILE   Save duplicate data to FILE
 -d        Show only files at a depth below home >= the Extensions dir (7)
 -v        Set logging level from INFO to DEBUG

"""

from colorama import init, Back, Fore  # BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE, RESET
from docopt import docopt
import graph_tool.all as gt
from hashlib import sha256
import json
import logging
from lxml import etree
import os
from os import path
import re
init(autoreset=True)


FILE = 1
DIRECTORY = 2
DT_DIR = 4
DT_REG = 8
MAX_FILES = 2
MIN_DEPTH = -1

EVAL_NONE = 2
EVAL_TRUE = 1
EVAL_FALSE = 0

INODE_ONLY = False
HASH_LABEL = True


class Clr:
    _color_it = lambda t, c, b: getattr(bool(b) and Back or Fore, c) + str(t) + \
                                getattr(bool(b) and Back or Fore, 'RESET')
    black = lambda t, b=True: Clr._color_it(t, 'BLACK', b)
    red = lambda t, b=True: Clr._color_it(t, 'RED', b)
    green = lambda t, b=True: Clr._color_it(t, 'GREEN', b)
    yellow = lambda t, b=True: Clr._color_it(t, 'YELLOW', b)
    blue = lambda t, b=True: Clr._color_it(t, 'BLUE', b)
    magenta = lambda t, b=True: Clr._color_it(t, 'MAGENTA', b)
    cyan = lambda t, b=True: Clr._color_it(t, 'CYAN', b)
    white = lambda t, b=True: Clr._color_it(t, 'WHITE', b)


class DuplicatesCompleted(Exception):
    pass


class SkipVolume(Exception):
    pass


class FileObj(object):

    def __init__(self, element_obj, namespace=''):
        self._obj = element_obj
        self._ns = namespace

    def findtext(self, element_path):
        val = self._obj.findtext(self._ns + element_path)
        if val is None:
            raise AttributeError
        return val

    def find(self, element_path):
        return self._obj.find(self._ns + element_path)

    def iter_grandchild(self, child, grandchild):
        c = self.find(child)
        if c is None:
            return []
        return c.iterfind(self._ns + grandchild)

    @property
    def obj(self):
        return self._obj


class ColorDiff(object):

    def __init__(self, dupl_file=None, verbose_log=False):
        self.digr = gt.Graph()
        self.type_count = {}
        self.home_vertex = None
        self.dupl_file = dupl_file
        self.gi = {}  # graph indexes: maps vertex "labels" to vertex objects

        # Create the internal property maps
        self.digr.vertex_properties['inode'] = self.digr.new_vertex_property('int')
        self.digr.vertex_properties['parent_inode'] = self.digr.new_vertex_property('int')
        self.digr.vertex_properties['filename_id'] = self.digr.new_vertex_property('string')
        self.digr.vertex_properties['filename_end'] = self.digr.new_vertex_property('string')
        self.digr.vertex_properties['name_type'] = self.digr.new_vertex_property('string')
        self.digr.vertex_properties['type'] = self.digr.new_vertex_property('vector<short>')
        self.digr.vertex_properties['alloc'] = self.digr.new_vertex_property('bool')
        self.digr.vertex_properties['used'] = self.digr.new_vertex_property('bool')
        self.digr.vertex_properties['fs_offset'] = self.digr.new_vertex_property('string')
        self.digr.vertex_properties['filesize'] = self.digr.new_vertex_property('string')
        self.digr.vertex_properties['src_files'] = self.digr.new_vertex_property('vector<short>')
        self.digr.vertex_properties['encrypted'] = self.digr.new_vertex_property('bool')
        self.digr.vertex_properties['eval'] = self.digr.new_vertex_property('bool')
        self.digr.vertex_properties['size'] = self.digr.new_vertex_property('string')
        self.digr.vertex_properties['mode'] = self.digr.new_vertex_property('string')
        self.digr.vertex_properties['uid'] = self.digr.new_vertex_property('string')
        self.digr.vertex_properties['gid'] = self.digr.new_vertex_property('string')
        self.digr.vertex_properties['nlink'] = self.digr.new_vertex_property('string')
        self.digr.vertex_properties['mtime'] = self.digr.new_vertex_property('string')
        self.digr.vertex_properties['ctime'] = self.digr.new_vertex_property('string')
        self.digr.vertex_properties['atime'] = self.digr.new_vertex_property('string')
        self.digr.vertex_properties['crtime'] = self.digr.new_vertex_property('string')
        self.digr.vertex_properties['color'] = self.digr.new_vertex_property('vector<float>')
        self.digr.vertex_properties['shape'] = self.digr.new_vertex_property('string')
        self.digr.vertex_properties['dir_depth'] = self.digr.new_vertex_property('short')
        self.digr.vertex_properties['gt_min_depth'] = self.digr.new_vertex_property('bool')

        # Set the "label" for vertices
        if INODE_ONLY:
            self._id = 'inode'
        elif HASH_LABEL:
            self._id = 'filename_id'

        # Initialize logging
        self._log_path = path.join(path.dirname(path.realpath(__file__)), '../log', "color_diff.log")
        with open(self._log_path, 'a') as fout:
            fout.write((' --  '*15)+'\n')
        log_format = '%(asctime)s %(levelname) 8s -- %(message)s'
        if verbose_log:
            log_level = logging.DEBUG
        else:
            log_level = logging.INFO
        logging.basicConfig(filename=self._log_path, level=log_level, format=log_format)
        logging.info('DFXML Color Diff initialized.')

    def deinit(self, clean=True, dup=False):
        if clean:
            logging.info('Execution completed cleanly. Shutting down.')
        elif dup:
            logging.info('Exiting. Duplicates written to file: %s' % self.dupl_file)
        else:
            logging.warning('Unclean shutdown. Did not finish graphing the diffs.')
        logging.shutdown()  # Flush and close all handlers

    def show_graph(self, fig_filename):
        # TODO: If this needs to support more than MAX_FILES==3, rewrite this
        num_drawn = 0.0  # To get floating point answer when dividing later
        next_logged = 0.25
        for vertex in self.digr.vertices():
            # Reset variables, just in case
            color = shape = None

            # How many files was this a part of?
            if len(self.digr.vp["src_files"][vertex]) >= 2:
                color = [0.502, 0., 0.502, 0.9]  # 'purple'
            elif 1 in self.digr.vp["src_files"][vertex]:
                color = [0.640625, 0, 0, 0.9]  # 'r'  # Red
            elif 2 in self.digr.vp["src_files"][vertex]:
                color = [0, 0, 0.640625, 0.9]  # 'b'  # Blue

            # File, directory, or other? Was it encrypted or not?
            enc = self.digr.vp['encrypted'][vertex]
            for t in self.digr.vp['type'][vertex]:
                # May redraw the same node multiple times, but that's better than losing data in the graph # TODO: Not true anymore
                if t == FILE:
                    if enc:
                        shape = 'hexagon'
                    else:
                        shape = 'circle'

                elif t == DIRECTORY:
                    if enc:
                        shape = 'double_triangle'
                    else:
                        shape = 'triangle'
                else:
                    # Unknown file types
                    color = [0, 0.749, 0.749, 0.9]  # Cyan
                    shape = 'square'

            self.digr.vp['color'][vertex] = color
            self.digr.vp['shape'][vertex] = shape

            # Log progress
            num_drawn += 1
            if (num_drawn/self.digr.num_vertices()) >= next_logged:
                per = str(int(next_logged*100)) + '%'
                logging.debug('Drawn %s of the nodes in the graph (%d/%d)' % (per, num_drawn, self.digr.num_vertices()))
                if next_logged == 0.25:
                    next_logged = 0.5
                elif next_logged == 0.5:
                    next_logged = 0.75
                elif next_logged == 0.75:
                    next_logged = 1.0

        # Continue drawing here
        vpen = self.digr.new_vertex_property('float')
        vpen.a = 0.2
        epen = self.digr.new_edge_property('float')
        epen.a = 0.5
        marker = self.digr.new_edge_property('float')
        marker.a = 2.5
        gt.graph_draw(self.digr,
                      vertex_fill_color=self.digr.vp['color'],
                      vertex_shape=self.digr.vp['shape'],
                      vertex_pen_width=vpen,
                      edge_pen_width=epen,
                      edge_marker_size=marker,
                      )

    def add_from_file(self, file_path, img_file_id=0):
        """
        Given the path to a DFXML file, add nodes and edges to the digraph
        representing its fileobjects.

        :param file_path: Path to the DFXML file from which to create the digraph.
        :type file_path: str
        :param img_file_id: ID number for the image file being processed. Used
                            to identify file objects that are common or unique
                            to each of the images.
        :type img_file_id: int
        :return: None
        :rtype: None
        """
        logging.info('Beginning import from file: %s' % file_path)
        xml_tree_root = etree.parse(file_path).getroot()
        ns = '{http://www.forensicswiki.org/wiki/Category:Digital_Forensics_XML}'
        logging.info('DFXML converted to element tree. Importing into the graph.')

        ex_pat_dot = re.compile('/\.\.?$')
        ex_pat_shadow = re.compile('^/?home/\.shadow/(.+)')
        in_pat_home = re.compile('^/?home$')
        in_pat_shadow = re.compile('^/?home/\.shadow$')
        in_pat_vault = re.compile('^/?home/\.shadow/[0-9a-z]*?/vault/user/')
        enc_pat = re.compile('/ECRYPTFS_FNEK_ENCRYPTED\.([^/]*)$')

        # Node info storage
        inode_paths = {}
        duplicates = []
        self.type_count = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0}

        edges_to_add = []
        num_skipped_files = 0
        num_duplicate_parent_dirs = 0
        num_unallocated = 0
        num_unused = 0

        for vol in xml_tree_root.iterfind(ns + 'volume'):
            for file_obj in vol.iterfind(ns + 'fileobject'):
                file_obj = FileObj(file_obj, ns)

                # Get the filename
                try:
                    filename = str(file_obj.findtext('filename'))
                except AttributeError:
                    filename = None
                # else:
                #     if filename.startswith('EFI-SYSTEM'):
                #         raise SkipVolume

                # Get allocation status
                try:
                    alloc = int(file_obj.findtext('alloc'))
                except AttributeError:
                    try:
                        alloc = int(file_obj.findtext('unalloc'))
                    except AttributeError:
                        logging.critical('File object has neither an alloc or unalloc tag: %s' % filename)
                        continue
                    else:
                        alloc = 1 - alloc
                alloc = bool(alloc)
                if not alloc:
                    # TODO: Dr. Ahn wants these files to be included for some reason
                    num_unallocated += 1
                    continue

                # Get used status
                try:
                    used = int(file_obj.findtext('used'))
                except AttributeError:
                    try:
                        used = int(file_obj.findtext('unused'))
                    except AttributeError:
                        logging.critical('File object has neither a used or unused tag: %s' % filename)
                        continue
                    else:
                        used = 1 - used
                used = bool(used)
                if not used:
                    num_unused += 1
                    continue

                # TODO: Figure out what to do with any files that passed tests up to this point but don't have a name
                if filename is None:
                    filename = str(etree.tostring(file_obj.find('id')))
                    print(filename)  # TODO: Remove this, replace with heuristics that determine if the vertex is worth keeping
                    continue

                # Exclude all files that end in '/.' or '/..'
                if re.search(ex_pat_dot, filename):
                    continue

                skip_add_edge = False
                is_home = False
                if re.search(in_pat_home, filename):
                    # Include 'home' and 'home/.shadow' so that other file objects can create edges with them
                    skip_add_edge = True
                    is_home = True
                elif re.search(in_pat_shadow, filename):
                    pass
                elif not re.search(ex_pat_shadow, filename):
                    # Exclude all files that don't start with 'home/.shadow/'
                    continue

                # Extract all pertinent information
                inode_num = int(file_obj.findtext('inode'))
                basename = path.basename(filename)
                parent_obj = int(file_obj.find('parent_object').findtext(ns + 'inode'))
                meta_type = int(file_obj.findtext('meta_type'))
                self.type_count[meta_type] += 1
                encrypted = bool(re.search(enc_pat, filename))
                filename_id = sha256(filename.encode('utf-8')).hexdigest()

                # Get depth from /home
                dir_depth = get_dir_depth(filename)
                # Files of interest to us should be in the .../vault/user/ dir and have a depth of at least 7
                # (when we're filtering, that is)
                gt_min_depth = bool(re.match(in_pat_vault, filename)) and dir_depth >= MIN_DEPTH

                fs_offset = float('inf')
                for fs in file_obj.iter_grandchild('byte_runs', 'byte_run'):
                    # Get the lowest offset of the file
                    _off = fs.get('fs_offset')
                    if _off is None:
                        continue
                    else:
                        _off = int(_off)

                    if _off < fs_offset:
                        fs_offset = _off
                if fs_offset == float('inf'):
                    fs_offset = '?'

                filesize = '?'
                try:
                    # Try to use the DFXML-computed length first
                    filesize = file_obj.findtext('filesize')
                except AttributeError:
                    # Iterate through the byte runs and sum their lengths
                    _sum = 0
                    for r in file_obj.iter_grandchild('byte_runs', 'byte_run'):
                        _sum += int(r['len'])
                    if _sum > 0:
                        filesize = _sum

                attrs = {"inode": inode_num,
                         "parent_inode": parent_obj,
                         # "filename": filename,
                         "filename_id": filename_id,
                         "filename_end": filename[-13:],
                         "name_type": file_obj.findtext('name_type'),
                         "type": (meta_type,),  # Needs to be hashable for Graphviz to not choke
                         "alloc": alloc,
                         "used": used,
                         "fs_offset": str(fs_offset),
                         "filesize": str(filesize),
                         "src_files": (img_file_id,),  # Needs to be hashable for Graphviz to not choke
                         "encrypted": encrypted,
                         "eval": EVAL_NONE,  # Used for trimming the graph
                         "dir_depth": dir_depth,
                         "gt_min_depth": gt_min_depth,
                         }

                # Stubborn parameters
                for k in ("size",
                          "mode",
                          "uid",
                          "gid",
                          "nlink",
                          "mtime",
                          "ctime",
                          "atime",
                          "crtime"):
                    try:
                        attrs[k] = file_obj.findtext(k)
                    except AttributeError:
                        attrs[k] = '?'

                # Store information about the node
                try:
                    _id = attrs[self._id]
                except KeyError:
                    _id = basename

                if inode_num in inode_paths and inode_paths[inode_num] != _id:
                    num_duplicate_parent_dirs += 1
                else:
                    inode_paths[inode_num] = _id

                # Make sure we don't try to double-add a node in the digraph
                if _id in self.gi.keys():
                    num_skipped_files += 1
                    dup_ver = self.gi[_id]
                    self.digr.vp["type"][dup_ver].append(meta_type)
                    if img_file_id not in self.digr.vp["src_files"][dup_ver]:
                        self.digr.vp["src_files"][dup_ver].append(img_file_id)
                    if img_file_id == 1:
                        # Save information on the duplicates for printing later
                        duplicates.append((_id, attrs))
                    continue

                # Add node and edge to the graph
                vertex = self.digr.add_vertex()
                self.gi[_id] = vertex
                for a in attrs:
                    if a in ('type', 'src_files'):
                        self.digr.vp[a][vertex] = (attrs[a])
                    else:
                        self.digr.vp[a][vertex] = attrs[a]

                if is_home:
                    self.home_vertex = vertex
                if not skip_add_edge:
                    edges_to_add.append((parent_obj, int(vertex)))

        logging.info("Done importing.")
        logging.debug("Number of skipped (duplicate) files: %d" % num_skipped_files)
        logging.debug("Number of unallocated files: %d" % num_unallocated)
        logging.debug("Number of allocated but unused files: %d" % num_unused)
        logging.debug("Number of duplicate parent directory entries: %d" % num_duplicate_parent_dirs)
        logging.debug("File count by type: %s" % self.type_count)
        type_sum = 0
        for i in self.type_count:
            type_sum += self.type_count[i]
        logging.info("Total imported file objects: %d" % type_sum)

        if img_file_id == 1 and self.dupl_file is not None:
            self._save_duplicate_info(duplicates)

        for u, v in edges_to_add:
            if INODE_ONLY:
                self.digr.add_edge(u, v)
            else:  # Includes when HASH_LABEL == True
                self.digr.add_edge(self.gi[inode_paths[u]], v)

    def _save_duplicate_info(self, duplicates):
        """
        Create a file containing information about the duplicates in the DFXML
        that was processes. Output file's path should have been passed to the
        class constructor on instantiation.

        :param duplicates: List of 2-tuples: (original vertex index, attribute
                           dict of the duplicate)
        :type duplicates: list
        :return: None
        :rtype: None
        """
        dstring = ' '
        d_fields = (('inode', '6'), ('parent_inode', '6'), ('name_type', '2'), ('type', '2'), ('alloc', '2'),
                    ('used', '2'), ('mode', '5'), ('nlink', '3'), ('uid', '5'), ('gid', '5'), ('fs_offset', '12'),
                    ('filesize', '8'), ('mtime', '20'), ('ctime', '20'), ('atime', '20'), ('crtime', '20'),
                    ('filename_id', '18'), ('filename_end', '13'))
        for k, n in d_fields:
            dstring += '% ' + n + 's|'
        header = dstring % ("inode", "pinode", "nt", "ty", "al", "ud", "mode", "nlk", "uid", "gid", "Start",
                            "Length", "Modified Time", "inode Changed Time", "Accessed Time", "Created Time",
                            "Filename Hash Tail", "Filename Tail")
        break_str = Clr.green(('--   ' * ((len(header) / 5) + 1))[:len(header)], False)
        header = Clr.yellow(Clr.black(header, False)) + '\n'
        line_count = 0

        with open(self.dupl_file, 'w') as dout:
            dout.write("\nDuplicates:"),
            for x, y in duplicates:
                dout.write('\n')
                if not line_count % 10:
                    dout.write(header)
                line_count += 1

                x_fields = []
                y_fields = []
                for k, n in d_fields:
                    if k == 'filename_id':
                        # Display only the last n characters of the hash
                        xf = self.digr.vp[k][self.gi[x]][0-int(n):]
                        yf = y[k][0-int(n):]
                    else:
                        xf = self.digr.vp[k][self.gi[x]]
                        yf = y[k]
                        if k == 'type':
                            if len(xf) > 2:
                                xf = '!' + str(xf[0])
                            elif len(xf) == 2:
                                xf = str(xf[0]) + str(xf[1])
                            else:
                                xf = xf[0]

                            if len(yf) > 2:
                                yf = '!' + str(yf[0])
                            elif len(yf) == 2:
                                yf = str(yf[0]) + str(yf[1])
                            else:
                                yf = yf[0]

                    if xf == '?':
                        xf = Clr.cyan(('% ' + n + 's') % '?', False)

                    x_fields.append(xf)

                    if xf == yf:
                        y_fields.append(yf)
                    else:
                        if y[k] == '?':
                            y_fields.append(Clr.blue(' ' * (int(n) - 1) + Clr.cyan('?', False)))
                        else:
                            y_fields.append(Clr.blue(('% ' + n + 's') % yf))

                dout.write(dstring % tuple(x_fields) + '\n')
                dout.write(dstring % tuple(y_fields) + '\n')
                dout.write(break_str)
            dout.write('\n\n')
        raise DuplicatesCompleted

    def trim_unuseful(self, filter_depth=False):
        """
        Remove unuseful vertices from the graph. This is the entry point to the
        recursive method _check_eval() that starts the process with all the
        child vertices of "home".

        :param filter_depth: If True, all nodes with a depth < MIN_DEPTH will
                             also be removed from the graph.
        :type filter_depth: bool
        :return: None
        :rtype: None
        """
        if self.home_vertex is None:
            raise TypeError('Must generate the graph before trimming it.')

        deg_before = self.digr.num_vertices()

        for n in self.home_vertex.out_neighbours():
            # This should only have one item (.shadow), but just in case...
            self._check_eval(n)

        deg_diff = deg_before - self.digr.num_vertices()

        logging.info('Finished trimming %d unuseful nodes from the graph. Distinct nodes and their parents remain.'
                     % deg_diff)

        if filter_depth:
            # Using an actual filter is faster, but I couldn't get the stupid thing to work right.
            # self.digr.set_vertex_filter(None)  # Clear any previously set vertex filters
            # self.digr.set_vertex_filter(self.digr.vp['gt_min_depth'])
            # logging.debug('Filtered all vertices with dir depth < %d' % MIN_DEPTH)
            rm_verts = []
            for v in self.digr.vertices():
                if not self.digr.vp['gt_min_depth'][v]:
                    rm_verts.append(v)
            self.digr.remove_vertex(rm_verts)
            logging.debug('Removed all vertices with dir depth < %d' % MIN_DEPTH)

    def _check_eval(self, vertex):
        """
        Recursively search successor vertices, evaluating their usefulness. A
        vertex is useful if:

        1. Any of its children are useful, or
        2. It was listed in fewer than the max number of files (it changed at
           some point)

        :param vertex: The vertex object to evaluate.
        :type vertex: Vertex
        :return: True (useful, keep) or False (not useful, delete)
        :rtype: bool
        """
        # Check if this node has already been evaluated
        if self.digr.vp["eval"][vertex] != EVAL_NONE:
            return self.digr.vp["eval"][vertex]

        # If this node is useful by itself, no need to check its children
        if len(self.digr.vp["src_files"][vertex]) < MAX_FILES:
            self.digr.vp["eval"][vertex] = EVAL_TRUE
            return True

        children_to_remove = []
        any_children_true = False
        for c in vertex.out_neighbours():
            _e = self._check_eval(c)
            if not _e:
                children_to_remove.append(c)
            any_children_true = any_children_true or _e

        # Remove unneeded children
        for c in children_to_remove:
            self.gi.pop(self.digr.vp[self._id][c])
        self.digr.remove_vertex(children_to_remove)

        self.digr.vp["eval"][vertex] = any_children_true
        return any_children_true


class _ExtensionSubTree(object):

    def __init__(self, start_vertex):
        """
        Using the start_vertex, gather basic data about this sub-graph.

        :param start_vertex:
        :type start_vertex: graph_tool.Vertex
        :return:
        """
        self._is_valid_extension = True  # Innocent until proven guilty
        self.digr = start_vertex.get_graph(start_vertex)

        # Find the top-most vertex
        self._top_vertex = self._get_top_vertex(start_vertex)

        # Determine if top vertex is a dir and has only dir children
        if not vertex_is_dir(self._top_vertex) or not self._children_all_dirs():
            self._is_valid_extension = False

        # Gather a list of all vertices in this sub-graph
        self._all_vertices = self._get_all_vertices()

    @property
    def is_valid(self):
        return self._is_valid_extension

    @property
    def vertices(self):
        """
        Return an iterator over the vertices in this subgraph.

        :return: Iterator over the vertices in this subgraph.
        :rtype: list_iterator
        """
        return self._all_vertices.__iter__()

    @staticmethod
    def _get_top_vertex(vertex):
        while True:
            if vertex.in_degree() == 0:
                return vertex
            elif vertex.in_degree() == 1:
                vertex = list(vertex.in_neighbours())[0]
            else:
                raise TypeError('Start vertex is in a non-tree graph.')

    def _children_all_dirs(self):
        # Top vertex must have at least one neighbor to pass the test
        all_dirs = bool(self._top_vertex.out_degree())
        for v in self._top_vertex.out_neighbours():
            all_dirs &= vertex_is_dir(v)
        return all_dirs

    def _get_all_vertices(self, vertex=None):
        """
        Generate and return a list of all the vertices in this subgraph.

        :return: A list of the vertex objects belonging to this subgraph.
        :rtype: list
        """
        if vertex is None:
            vertex = self._top_vertex
        v = [vertex]
        for n in vertex.out_neighbours():
            v += self._get_all_vertices(n)
        return v


def vertex_is_dir(vertex, strict=False):
    """
    Given a vertex, return whether it represents a directory.

    :param vertex: The vertex to test.
    :type vertex: graph_tool.Vertex
    :param strict: If True, the first type stored in the vertex property
        vector must be the one that indicates a directory. Otherwise, any of
        the values in the vector that match will return True.
    :type strict: bool
    :return: Whether the vertex represents a directory.
    :rtype: bool
    """
    graph = vertex.get_graph(vertex)
    if strict:
        return graph.vp['type'][vertex][0] == 2

    for t in graph.vp['type'][vertex]:
        if t == 2:
            return True
    return False


def get_dir_depth(filename):
    """
    Calculate how many directories deep the filename is.

    :param filename: The path to be split and counted.
    :type filename: str
    :return: The number of directory levels in the filename.
    :rtype: int
    """
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


FILTERED_MIN_DEPTH = get_dir_depth('/home/.shadow/<user ID>/vault/user/<encrypted Extensions>/<encrypted extension ID>/')


def main(args):
    # Set min depth
    global MIN_DEPTH
    if args['-d']:
        MIN_DEPTH = FILTERED_MIN_DEPTH

    try:
        img_dir = os.environ['DBLING_IMGS']
        if not path.isdir(img_dir):
            raise KeyError
    except KeyError:
        with open(path.join(path.dirname(path.realpath(__file__)), 'dbling_conf.json')) as fin:
            img_dir = json.load(fin)['img_dir']

    imgs = os.listdir(img_dir)
    imgs.sort(reverse=True)
    to_compare = []
    dfxml_ext = re.compile('\.df\.xml$')

    diff = ColorDiff(dupl_file=args['-f'], verbose_log=args['-v'])
    for i in imgs:
        i_pth = path.join(img_dir, i)
        # For info on what this does and what it means, see:
        # https://docs.python.org/3/library/os.html#os.stat_result
        # http://www.virtualblueness.net/Ext2fs-overview/Ext2fs-overview-0.1-10.html#ss10.2
        # http://stackoverflow.com/questions/4041480/i-mode-file-type-value-of-16
        f_type = os.stat(i_pth).st_mode >> 12

        if not f_type == DT_REG:
            continue

        if not re.search(dfxml_ext, i):
            # Only consider files ending in ".df.xml"
            continue

        to_compare.append(path.join(img_dir, i))
        if len(to_compare) == MAX_FILES:
            break

    to_compare.sort()
    for i, n in zip(to_compare, range(len(to_compare))):
        try:
            diff.add_from_file(i, n+1)
        except DuplicatesCompleted:
            diff.deinit(False, dup=True)
            return
        except:
            diff.deinit(False)
            raise

    try:
        diff.trim_unuseful(filter_depth=args['-d'])
        diff.show_graph('testfig.png')
    except:
        diff.deinit(False)
        raise
    diff.deinit()

if __name__ == '__main__':
    main(docopt(__doc__))
