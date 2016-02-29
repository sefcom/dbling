#!/usr/bin/env python3
"""
Usage: graph_diff.py [options]

Options:
 -f FILE   Save duplicate data to FILE
 -d        Show only files at a depth below home >= the Extensions dir (7)
 -v        Set logging level from INFO to DEBUG

"""

import json
import logging
import os
import re
from hashlib import sha256
from os import path

import graph_tool.all as gt
from docopt import docopt
from lxml import etree

from centroid import get_tree_top
import clr
from const import *
import crx
from crx import make_graph_from_dir
import util


FILE = 1
DIRECTORY = 2
DT_DIR = 4
DT_REG = 8
MAX_FILES = 2

KNOWN_EXT_DIR = None

INODE_ONLY = False
HASH_LABEL = True


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


class _GraphDiff(object):

    def __init__(self, dupl_file=None):
        self.digr = gt.Graph()
        self.type_count = {}
        self.home_vertex = None
        self.dupl_file = dupl_file
        self._filter_depth = False
        self.gi = {}  # graph indexes: maps vertex "labels" to vertex objects

        # Create the internal property maps
        self.digr.vp['inode'] = self.digr.new_vertex_property('int')
        self.digr.vp['parent_inode'] = self.digr.new_vertex_property('int')
        self.digr.vp['filename'] = self.digr.new_vertex_property('string')
        self.digr.vp['filename_id'] = self.digr.new_vertex_property('string')
        self.digr.vp['filename_end'] = self.digr.new_vertex_property('string')
        self.digr.vp['name_type'] = self.digr.new_vertex_property('string')
        self.digr.vp['type'] = self.digr.new_vertex_property('vector<short>')
        self.digr.vp['alloc'] = self.digr.new_vertex_property('bool')
        self.digr.vp['used'] = self.digr.new_vertex_property('bool')
        self.digr.vp['fs_offset'] = self.digr.new_vertex_property('string')
        self.digr.vp['filesize'] = self.digr.new_vertex_property('string')
        self.digr.vp['src_files'] = self.digr.new_vertex_property('vector<short>')
        self.digr.vp['encrypted'] = self.digr.new_vertex_property('bool')
        self.digr.vp['eval'] = self.digr.new_vertex_property('bool')
        self.digr.vp['size'] = self.digr.new_vertex_property('string')
        self.digr.vp['mode'] = self.digr.new_vertex_property('string')
        self.digr.vp['uid'] = self.digr.new_vertex_property('string')
        self.digr.vp['gid'] = self.digr.new_vertex_property('string')
        self.digr.vp['nlink'] = self.digr.new_vertex_property('string')
        self.digr.vp['mtime'] = self.digr.new_vertex_property('string')
        self.digr.vp['ctime'] = self.digr.new_vertex_property('string')
        self.digr.vp['atime'] = self.digr.new_vertex_property('string')
        self.digr.vp['crtime'] = self.digr.new_vertex_property('string')
        self.digr.vp['color'] = self.digr.new_vertex_property('vector<float>')
        self.digr.vp['shape'] = self.digr.new_vertex_property('string')
        self.digr.vp['graph_size'] = self.digr.new_vertex_property('int', val=5)
        self.digr.vp['dir_depth'] = self.digr.new_vertex_property('short')
        self.digr.vp['gt_min_depth'] = self.digr.new_vertex_property('bool')
        self.digr.vp['keeper'] = self.digr.new_vertex_property('bool', val=True)

        # Set the "label" for vertices
        if INODE_ONLY:
            self._id = 'inode'
        elif HASH_LABEL:
            self._id = 'filename_id'

        # Queue for removing vertices
        self._to_remove = []

        # Regular expressions for filtering files
        self.ex_pat_dot = re.compile('/\.\.?$')
        self.ex_pat_shadow = re.compile('^/?home/\.shadow/(.+)')
        self.in_pat_home = re.compile('^/?home$')
        self.in_pat_shadow = re.compile('^/?home/\.shadow$')

    def deinit(self, clean=True, dup=False):
        if clean:
            logging.info('Execution completed cleanly. Shutting down.')
        elif dup and self.dupl_file is not None:
            logging.info('Exiting. Duplicates written to file: %s' % self.dupl_file)
        else:
            logging.warning('Unclean shutdown. Did not finish processing the diffs.')
        logging.shutdown()  # Flush and close all handlers

    def graph_copy(self):
        """
        Return a copy of the graph object.

        :return: A copy of the graph.
        :rtype: graph_tool.Graph
        """
        return self.digr.copy()

    def show_graph(self, digr=None):
        # TODO: If this needs to support more than MAX_FILES==3, rewrite this
        if digr is None:
            digr = self.digr

        num_drawn = 0.0  # To get floating point answer when dividing later
        next_logged = 0.25
        for vertex in digr.vertices():
            # Reset variables, just in case
            color = shape = None

            # How many files was this a part of?
            if len(digr.vp["src_files"][vertex]) >= 2:
                color = [0.502, 0., 0.502, 0.9]  # 'purple'
            elif 1 in digr.vp["src_files"][vertex] or not len(digr.vp["src_files"][vertex]):
                color = [0.640625, 0, 0, 0.9]  # 'r'  # Red
            elif 2 in digr.vp["src_files"][vertex]:
                color = [0, 0, 0.640625, 0.9]  # 'b'  # Blue

            # File, directory, or other? Was it encrypted or not?
            enc = digr.vp['encrypted'][vertex]
            for t in digr.vp['type'][vertex]:
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
                break

            if not len(digr.vp['color'][vertex]):  # Only set color if we didn't already set it
                # import pdb; pdb.set_trace()
                digr.vp['color'][vertex] = color
            digr.vp['shape'][vertex] = shape

            if digr.vp['inode'][vertex] == KNOWN_EXT_DIR:
                digr.vp['color'][vertex] = [0.8, 0, 0.8, 0.9]
                digr.vp['graph_size'][vertex] = 10
            else:
                digr.vp['graph_size'][vertex] = 5

            if not digr.vp['keeper'][vertex]:
                digr.vp['color'][vertex] = [0, 0, 0, 0.8]

            # Log progress
            num_drawn += 1
            if (num_drawn/digr.num_vertices()) >= next_logged:
                per = str(int(next_logged*100)) + '%'
                logging.debug('Drawn %s of the nodes in the graph (%d/%d)' % (per, num_drawn, digr.num_vertices()))
                if next_logged == 0.25:
                    next_logged = 0.5
                elif next_logged == 0.5:
                    next_logged = 0.75
                elif next_logged == 0.75:
                    next_logged = 1.0

        # Continue drawing here
        vpen = digr.new_vertex_property('float')
        vpen.a = 0.2
        epen = digr.new_edge_property('float')
        epen.a = 0.5
        marker = digr.new_edge_property('float')
        marker.a = 2.5
        gt.graph_draw(digr,
                      vertex_fill_color=digr.vp['color'],
                      vertex_shape=digr.vp['shape'],
                      # vertex_size=self.digr.vp['graph_size'],
                      vertex_pen_width=vpen,
                      edge_pen_width=epen,
                      edge_marker_size=marker,
                      display_props=[digr.vp['filename_end'],
                                     digr.vp['inode'],
                                     digr.vp['dir_depth'],
                                     digr.vp['gt_min_depth']],
                      )

    def add_from_file(self, file_path, img_file_id=1):
        """
        Given the path to a DFXML file, add nodes and edges to the digraph
        representing its fileobjects.

        :param file_path: Path to the DFXML file from which to create the digraph.
        :type file_path: str
        :param img_file_id: ID number for the image file being processed. Used
            to identify file objects that are common or unique to each of the
            images.
        :type img_file_id: int
        :return: None
        :rtype: None
        """
        logging.info('Beginning import from file: %s' % file_path)
        xml_tree_root = etree.parse(file_path).getroot()
        ns = '{http://www.forensicswiki.org/wiki/Category:Digital_Forensics_XML}'
        logging.info('DFXML converted to element tree. Importing into the graph.')

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
                if re.search(self.ex_pat_dot, filename):
                    continue

                skip_add_edge = False
                is_home = False
                if re.search(self.in_pat_home, filename):
                    # Include 'home' and 'home/.shadow' so that other file objects can create edges with them
                    skip_add_edge = True
                    is_home = True
                elif re.search(self.in_pat_shadow, filename):
                    pass
                elif not re.search(self.ex_pat_shadow, filename):
                    # Exclude all files that don't start with 'home/.shadow/'
                    continue

                # Extract all pertinent information
                inode_num = int(file_obj.findtext('inode'))
                basename = path.basename(filename)
                parent_obj = int(file_obj.find('parent_object').findtext(ns + 'inode'))
                meta_type = int(file_obj.findtext('meta_type'))
                self.type_count[meta_type] += 1
                encrypted = bool(re.search(ENC_PAT, filename))
                filename_id = sha256(filename.encode('utf-8')).hexdigest()

                # Coerce the parent object to be a directory if it isn't
                try:
                    if self.digr.vp['type'][parent_obj][0] != 2:
                        self.digr.vp['type'][parent_obj][0] = 2
                        logging.debug('Coerced inode %d to have file type 2 (dir)' % self.digr.vp['inode'][parent_obj])
                except ValueError:
                    # The listed parent inode must not exist in the graph
                    pass

                # Get depth from /home
                dir_depth = util.get_dir_depth(filename)
                # Files of interest to us should be in the .../vault/user/ dir and have a depth of at least 7
                # (when we're filtering, that is)
                gt_min_depth = bool(re.match(IN_PAT_VAULT, filename)) and dir_depth >= MIN_DEPTH

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
                         "filename_end": path.basename(filename[-13:]),
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
                    dup_ver = self.gi[inode_paths[inode_num]]
                    # If the depth of the new vertex is lower (closer to /home), replace the old one
                    if attrs['dir_depth'] < self.digr.vp['dir_depth'][dup_ver]:
                        # Mark the duplicate vertex for removal later
                        # vertices_to_remove.append(dup_ver)
                        # Remove the edge from the "to add" list of the old vertex
                        try:
                            edges_to_add.remove((self.digr.vp['parent_inode'][dup_ver], int(dup_ver)))
                        except ValueError:
                            # There was no matching entry in the "to add" list
                            pass
                            # edges_to_remove.append((self.digr.vp['parent_inode'][dup_ver], int(dup_ver)))
                            # print('%s was not in the list of edges to add' % ((self.digr.vp['parent_inode'][dup_ver], int(dup_ver)),))
                        edges_to_add.append((parent_obj, int(dup_ver)))
                        for a in attrs:
                            if a in ('type', 'src_files'):
                                self.digr.vp[a][dup_ver] = (attrs[a])
                            else:
                                self.digr.vp[a][dup_ver] = attrs[a]
                        inode_paths[inode_num] = _id
                        self.gi[_id] = dup_ver
                        continue

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
                    self.digr.vp['color'][vertex] = [0, 0.8, 0, 0.9]
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
                pass
            else:  # Includes when HASH_LABEL == True
                u = self.gi[inode_paths[u]]

            if u == v:  # Don't add edges between a vertex and itself
                continue

            if self.digr.vertex(v).in_degree():
                for p in self.digr.vertex(v).in_neighbours():
                    self.digr.remove_edge(self.digr.edge(p, self.digr.vertex(v)))

            self.digr.add_edge(u, v, False)

    def add_from_mount(self, mount_point):
        # TODO: Do we need to keep from adding duplicates to this graph?
        logging.info('Beginning import from mount point: %s' % mount_point)
        make_graph_from_dir(mount_point, self.digr)
        self.home_vertex = get_tree_top(self.digr)

        # Set the default value for the keeper flag as True for all vertices
        for v in self.digr.vertices():
            self.digr.vp['keeper'][v] = True

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
        break_str = clr.green(('--   ' * ((len(header) / 5) + 1))[:len(header)], False)
        header = clr.yellow(clr.black(header, False)) + '\n'
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
                        xf = clr.cyan(('% ' + n + 's') % '?', False)

                    x_fields.append(xf)

                    if xf == yf:
                        y_fields.append(yf)
                    else:
                        if y[k] == '?':
                            y_fields.append(clr.blue(' ' * (int(n) - 1) + clr.cyan('?', False)))
                        else:
                            y_fields.append(clr.blue(('% ' + n + 's') % yf))

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

        self._filter_depth = filter_depth

        deg_before = self.digr.num_vertices()
        trim_stats = {'min_depth': 0,
                      'no_parent': 0}

        for n in self.home_vertex.out_neighbours():
            # This should only have one item (.shadow), but just in case...
            self._check_eval(n)

        # This isn't very efficient, but we need to remove all vertices with no in-neighbors
        for v in self.digr.vertices():
            # if v in self._to_remove:
            if not self.digr.vp['keeper'][v]:
                continue
            if filter_depth and not self.digr.vp['gt_min_depth'][v]:
                self.digr.vp['keeper'][v] = False
                self._to_remove.append(v)
                trim_stats['min_depth'] += 1
            elif v == self.home_vertex:
                continue
            elif not v.in_degree() and not v.out_degree():
                self.digr.vp['keeper'][v] = False
                self._to_remove.append(v)
                trim_stats['no_parent'] += 1
        # print(self.home_vertex in self._to_remove)

        # for v in self._to_remove:
        #     self.digr.vp['color'][v] = [0, 0, 0, 0.8]
        #     self.digr.vp['keeper'][v] = False

        if filter_depth:
            # Using an actual filter is faster, but I couldn't get the stupid thing to work right.
            self.digr.clear_filters()  # Clear any previously set vertex filters
            # self.digr.set_vertex_filter(self.digr.vp['gt_min_depth'])
            self.digr.set_vertex_filter(self.digr.vp['keeper'])
            self.digr.purge_vertices()

            # Get the straggler vertices
            for v in self.digr.vertices():
                if not v.in_degree() and not v.out_degree():
                    self.digr.vp['keeper'][v] = False
            self.digr.set_vertex_filter(self.digr.vp['keeper'])
            self.digr.purge_vertices()
            # self.digr.clear_filters()  # Clear any previously set vertex filters

            logging.debug('Graph now has %s objects' % self.digr.num_vertices())

        deg_diff = deg_before - self.digr.num_vertices()

        logging.info('Finished trimming %d unuseful nodes from the graph.' % deg_diff)
        logging.debug('Below min depth:  %d    No parent node:  %d' % (trim_stats['min_depth'], trim_stats['no_parent']))

    def _check_eval(self, vertex):
        raise NotImplementedError


class ColorDiff(_GraphDiff):

    def __init__(self, dupl_file=None):
        super().__init__(dupl_file=dupl_file)
        logging.info('DFXML ' + clr.black(clr.red('C', False) +
                                          clr.green('O', False) +
                                          clr.magenta('L', False) +
                                          clr.yellow('O', False) +
                                          clr.cyan('R', False)) + ' Diff initialized.')

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
            # logging.debug('Skipping eval of node: %s' % self.digr.vp[self._id][vertex])
            return self.digr.vp["eval"][vertex]

        # If this node is useful by itself, no need to check its children
        if len(self.digr.vp["src_files"][vertex]) < MAX_FILES:
            # logging.debug('Skipping eval of child nodes of node: %s' % self.digr.vp[self._id][vertex])
            self.digr.vp["eval"][vertex] = EVAL_TRUE
            return True

        any_children_true = False
        for c in vertex.out_neighbours():
            _e = self._check_eval(c)
            if not _e:
                self._to_remove.append(c)
            any_children_true = any_children_true or _e

        self.digr.vp["eval"][vertex] = any_children_true
        return any_children_true


class FilesDiff(_GraphDiff):

    def __init__(self):
        super().__init__()
        logging.info('DFXML Files Diff initialized.')

    def _check_eval(self, vertex, force_false=False):
        """
        Recursively search successor vertices, evaluating their usefulness. A
        vertex is useful if:

        1. Any of its children are useful
        2. At least one of the following is true:
          a. It is a leaf node
          b. It is at the depth of the Extensions directory and is an
             encrypted directory
          c. It is at the depth of either the Extensions directory or the
             <Extension ID> directory and has only non-empty directory
             successors

        When this recursive method is followed directly by another pass over
        the vertices to remove all that are not of minimum depth, the
        subgraphs that remain are prime candidates for extension directories.

        :param vertex: The vertex object to evaluate.
        :type vertex: Vertex
        :param force_false: Useful for when a vertex is found that violates a
            required condition, mark all successor vertices to the given
            vertex for deletion.
        :type force_false: bool
        :return: True (useful, keep) or False (not useful, delete)
        :rtype: bool
        """
        # Check if this node has already been evaluated
        if self.digr.vp["eval"][vertex] != EVAL_NONE:
            # logging.debug('Skipping eval of node: %s' % self.digr.vp[self._id][vertex])
            return self.digr.vp["eval"][vertex]

        if force_false:
            return self._force_false(vertex)

        # If this is at the same depth as the Extensions dir, it should be an encrypted directory
        if self.digr.vp['dir_depth'][vertex] == (FILTERED_MIN_DEPTH - 2) and \
                (not vertex_is_dir(vertex, self.digr) or not self.digr.vp['encrypted'][vertex]):
            self.check_warn_removal(vertex, 'not an encrypted dir at Extensions dir level')
            return self._force_false(vertex)

        # If this is at the same depth as the Extensions dir, it should have only dir children and grandchildren
        if self.digr.vp['dir_depth'][vertex] == FILTERED_MIN_DEPTH - 2:
            self.digr.vp['color'][vertex] = [0.8, 0.8, 0, 0.9]
            all_dir_children = vertex.out_degree() > 0
            for c in vertex.out_neighbours():  # Check children
                # break
                if not vertex_is_dir(c, self.digr):
                    all_dir_children = False
                    self.check_warn_removal(vertex, 'non-dir child vertex at Extension dir level')
                    break

                for gc in c.out_neighbours():  # Check grandchildren
                    depth_differs_by_two = (self.digr.vp['dir_depth'][gc] - self.digr.vp['dir_depth'][vertex]) == 2
                    if not depth_differs_by_two:
                        self._force_false(gc)
                        continue

                if not all_dir_children:
                    break
            if not all_dir_children:
                return self._force_false(vertex)

        # If this is at the same depth as the Extension ID dir, it should have only dir children
        if self.digr.vp['dir_depth'][vertex] == FILTERED_MIN_DEPTH - 1:
            all_dir_children = vertex.out_degree() > 0
            for c in vertex.out_neighbours():
                if not vertex_is_dir(c, self.digr):
                    all_dir_children = False
                    break
            if not all_dir_children:
                return self._force_false(vertex)

        any_children_true = vertex.out_degree() == 0  # Leaf nodes should be True by default, others False
        for c in vertex.out_neighbours():
            _e = self._check_eval(c)
            if not _e:
                self._to_remove.append(c)
                self.digr.vp['keeper'][c] = False
            any_children_true = any_children_true or _e

        self.digr.vp["eval"][vertex] = any_children_true
        if self._filter_depth:
            any_children_true = any_children_true and self.digr.vp['dir_depth'][vertex] >= MIN_DEPTH
        return any_children_true

    def _force_false(self, vertex):
        self.digr.vp['eval'][vertex] = EVAL_FALSE
        self._to_remove += list(vertex.out_neighbours())
        for c in vertex.out_neighbours():
            self._check_eval(c, force_false=True)
        return False

    def check_warn_removal(self, vertex, msg, v_prop='inode', warn_list=(KNOWN_EXT_DIR,)):
        if self.digr.vp[v_prop][vertex] in warn_list or not len(warn_list):
            logging.warning('Removing inode %d because: %s' % (self.digr.vp['inode'][vertex], msg))


def vertex_is_dir(vertex, graph, strict=False):
    """
    Given a vertex, return whether it represents a directory.

    :param vertex: The vertex to test.
    :type vertex: graph_tool.Vertex
    :param graph: The graph that vertex belongs to.
    :type graph: graph_tool.Graph
    :param strict: If True, the first type stored in the vertex property
        vector must be the one that indicates a directory. Otherwise, any of
        the values in the vector that match will return True.
    :type strict: bool
    :return: Whether the vertex represents a directory.
    :rtype: bool
    """
    if strict:
        return graph.vp['type'][vertex][0] == 2

    for t in graph.vp['type'][vertex]:
        if t == 2:
            return True
    return False


FILTERED_MIN_DEPTH = util.get_dir_depth('/home/.shadow/<user ID>/vault/user/<encrypted Extensions>/'
                                        '<encrypted extension ID>/<encrypted extension version>/')


def init_logging(log_file=None, verbose=False):
    if log_file is None:
        _log_path = path.join(path.dirname(path.realpath(__file__)), '../log', "graph_diff.log")
    else:
        _log_path = log_file

    # Initialize logging
    with open(_log_path, 'a') as fout:
        fout.write((' --  '*15)+'\n')
    log_format = '%(asctime)s %(levelname) 8s -- %(message)s'
    if verbose:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO
    logging.basicConfig(filename=_log_path, level=log_level, format=log_format)
    util.add_color_log_levels(center=True)


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

    init_logging(verbose=args['-v'])

    # Instantiate the diff object and process the files
    diff = ColorDiff(dupl_file=args['-f'])
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
        diff.show_graph()
    except:
        diff.deinit(False)
        raise
    diff.deinit()

if __name__ == '__main__':
    main(docopt(__doc__))
else:
    # This file was imported, so do all the necessary configuration
    crx.MIN_DEPTH = FILTERED_MIN_DEPTH
    MIN_DEPTH = FILTERED_MIN_DEPTH
    MAX_FILES = 1
