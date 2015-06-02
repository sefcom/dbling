#!/usr/bin/env python
"""
Usage: color_diff.py [-f FILE]

Options:
  -f FILE   Save duplicate data to FILE

Requires packages:
graphviz-dev
python-pydot
"""

from colorama import init, Back, Fore  # BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE, RESET
from copy import deepcopy as copy
from docopt import docopt
from hashlib import sha256
from io import StringIO
import json
import logging
from lxml import etree
from matplotlib import pyplot as plt
import networkx
import os
from os import path
import re
init(autoreset=True)


FILE = 1
DIRECTORY = 2
DT_DIR = 4
DT_REG = 8
MAX_FILES = 2
INODE_ONLY = False
HASH_LABEL = True


def _color_it(text, color, b):
    bf = bool(b) and Back or Fore
    return getattr(bf, color) + str(text) + bf.RESET


def make_yellow(text, b=True):
    return _color_it(text, 'YELLOW', b)


def make_red(text, b=True):
    return _color_it(text, 'RED', b)


def make_blue(text, b=True):
    return _color_it(text, 'BLUE', b)


def make_green(text, b=True):
    return _color_it(text, 'GREEN', b)


def make_cyan(text, b=True):
    return _color_it(text, 'CYAN', b)


def make_black(text, b=True):
    return _color_it(text, 'BLACK', b)


class DuplicatesCompleted(Exception):
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

    def __init__(self, dupl_file=None):
        self.digr = networkx.DiGraph()
        self.type_count = {}
        self.home_node_label = None
        self.dupl_file = dupl_file

        # Initialize logging
        self._log_path = path.join(path.dirname(path.realpath(__file__)), '../log', "color_diff.log")
        with open(self._log_path, 'a') as fout:
            fout.write((' --  '*15)+'\n')
        log_format = '%(asctime)s %(levelname) 8s -- %(message)s'
        logging.basicConfig(filename=self._log_path, level=logging.DEBUG, format=log_format)
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
        # Generate positions for all the nodes, edges
        pos = networkx.pydot_layout(self.digr, prog='dot', root='home')

        # TODO: If this needs to support more than MAX_FILES==3, rewrite this
        num_drawn = 0.0  # To get floating point answer when dividing later
        next_logged = 0.25
        for node, node_data in self.digr.nodes_iter(True):
            # Reset variables, just in case
            color = shape = None

            # How many files was this a part of?
            if len(node_data["src_files"]) >= 2:
                color = 'purple'
            elif 1 in node_data["src_files"]:
                color = 'r'  # Red
            elif 2 in node_data["src_files"]:
                color = 'b'  # Blue

            # File, directory, or other? Was it encrypted or not?
            for t in node_data['type']:
                # May redraw the same node multiple times, but that's better than losing data in the graph
                if t == FILE:
                    if node_data['encrypted']:
                        shape = 'h'  # Hexagon
                    else:
                        shape = 'o'  # Circle

                elif t == DIRECTORY:
                    if node_data['encrypted']:
                        shape = 'd'  # Diamond
                    else:
                        shape = '^'  # Triangle
                else:
                    # Unknown file types
                    color = 'c'
                    shape = 's'

                networkx.draw_networkx_nodes(self.digr, pos, [node], node_color=color, node_shape=shape)

            # Log progress
            num_drawn += 1
            if (num_drawn/len(self.digr)) >= next_logged:
                per = str(int(next_logged*100)) + '%'
                logging.debug('Drawn %s of the nodes in the graph (%d/%d)' % (per, num_drawn, len(self.digr)))
                if next_logged == 0.25:
                    next_logged = 0.5
                elif next_logged == 0.5:
                    next_logged = 0.75
                elif next_logged == 0.75:
                    next_logged = 1.0

        # Continue drawing here
        logging.info('Drawing edges, then saving the image.')
        networkx.draw_networkx_edges(self.digr, pos, alpha=0.8)

        plt.axis('off')
        plt.savefig(fig_filename)
        plt.show()

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
        vol = xml_tree_root.find(ns + 'volume')
        logging.info('DFXML converted to element tree. Importing into the graph.')

        ex_pat1 = re.compile('/\.\.?$')
        ex_pat2 = re.compile('^/?home/\.shadow/(.+)')
        ex_pat3 = re.compile('^/?home$')
        ex_pat4 = re.compile('^/?home/\.shadow$')
        enc_pat5 = re.compile('/ECRYPTFS_FNEK_ENCRYPTED\.([^/]*)$')

        # Node info storage
        inode_paths = {}
        duplicates = []
        self.type_count = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0}

        edges_to_add = []
        num_skipped_files = 0
        num_duplicate_parent_dirs = 0
        num_unallocated = 0
        num_unused = 0

        for file_obj in vol.iterfind(ns + 'fileobject'):
            file_obj = FileObj(file_obj, ns)

            # Get the filename
            try:
                filename = unicode(file_obj.findtext('filename'))
            except AttributeError:
                filename = None

            # Get allocation status
            try:
                alloc = file_obj.findtext('alloc')
            except AttributeError:
                try:
                    alloc = file_obj.findtext('unalloc')
                except AttributeError:
                    logging.critical('File object has neither an alloc or unalloc tag: %s' % filename)
                    raise
                else:
                    alloc = str(1 - int(alloc))
            if alloc == '0':
                # TODO: Dr. Ahn wants these files to be included for some reason
                num_unallocated += 1
                continue

            # Get used status
            try:
                used = file_obj.findtext('used')
            except AttributeError:
                try:
                    used = file_obj.findtext('unused')
                except AttributeError:
                    logging.critical('File object has neither a used or unused tag: %s' % filename)
                    raise
                else:
                    used = str(1 - int(used))
            if used == '0':
                num_unused += 1
                continue

            # TODO: Figure out what to do with any files that passed tests up to this point but don't have a name
            if filename is None:
                filename = unicode(etree.tostring(file_obj.find('id')))
                print(filename)  # TODO: Remove this

            # Exclude all files that end in '/.' or '/..'
            if re.search(ex_pat1, filename):
                continue

            skip_add_edge = False
            is_home = False
            if re.search(ex_pat3, filename):
                # Include 'home' and 'home/.shadow' so that other file objects can create edges with them
                skip_add_edge = True
                is_home = True
            elif re.search(ex_pat4, filename):
                pass
            elif not re.search(ex_pat2, filename):
                # Exclude all files that don't start with 'home/.shadow/'
                continue

            # Extract all pertinent information
            inode_num = int(file_obj.findtext('inode'))
            basename = path.basename(filename)
            parent_obj = int(file_obj.find('parent_object').findtext(ns + 'inode'))
            meta_type = int(file_obj.findtext('meta_type'))
            self.type_count[meta_type] += 1
            encrypted = bool(re.search(enc_pat5, filename))
            filename_id = sha256(filename.encode('utf-8')).hexdigest()

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
                     "fs_offset": fs_offset,
                     "filesize": filesize,
                     "src_files": (img_file_id,),  # Needs to be hashable for Graphviz to not choke
                     "encrypted": encrypted,
                     "eval": None,  # Used for trimming the graph
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
            if INODE_ONLY:
                _id = inode_num
            elif HASH_LABEL:
                _id = filename_id
            else:
                _id = basename

            if is_home:
                self.home_node_label = _id

            if inode_num in inode_paths and inode_paths[inode_num] != _id:
                num_duplicate_parent_dirs += 1
            else:
                inode_paths[inode_num] = _id

            # Make sure we don't try to double-add a node in the digraph
            if self.digr.has_node(_id):
                num_skipped_files += 1
                self.digr.node[_id]["type"] += (meta_type,)
                self.digr.node[_id]["src_files"] += (img_file_id,)
                if img_file_id == 1:
                    # Save information on the duplicates for printing later
                    duplicates.append((self.digr.node[_id], attrs))
                continue

            # Add node and edge to the graph
            self.digr.add_node(_id, attrs)
            if not skip_add_edge:
                edges_to_add.append((parent_obj, _id))

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
            break_str = make_green(('--   ' * ((len(header) / 5) + 1))[:len(header)], 0)
            header = make_yellow(make_black(header, 0)) + '\n'
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
                            xf = x[k][0-int(n):]
                            yf = y[k][0-int(n):]
                        else:
                            xf = x[k]
                            yf = y[k]
                            if k == 'type':
                                if len(xf) > 2:
                                    xf = '!' + str(xf[0])
                                elif len(xf) == 2:
                                    xf = str(xf[0]) + str(xf[1])
                                else:
                                    xf = xf[0]

                                if len(yf) > 1:
                                    yf = '!' + str(yf[0])
                                else:
                                    yf = yf[0]

                        if xf == '?':
                            xf = make_cyan(('% ' + n + 's') % '?', 0)

                        x_fields.append(xf)

                        if xf == yf:
                            y_fields.append(yf)
                        else:
                            if y[k] == '?':
                                y_fields.append(make_blue(' ' * (int(n) - 1) + make_cyan('?', 0)))
                            else:
                                y_fields.append(make_blue(('% ' + n + 's') % yf))

                    dout.write(dstring % tuple(x_fields) + '\n')
                    dout.write(dstring % tuple(y_fields) + '\n')
                    dout.write(break_str)
                dout.write('\n\n')
            raise DuplicatesCompleted

        for u, v in edges_to_add:
            if INODE_ONLY:
                self.digr.add_edge(u, v)
            else:  # Includes when HASH_LABEL == True
                self.digr.add_edge(inode_paths[u], v)

    def trim_unuseful(self):
        """
        Remove unuseful nodes from the graph. This is the entry point to the
        recursive method _check_eval() that starts the process with all the
        child nodes of "home".

        :return: None
        :rtype: None
        """
        if self.home_node_label is None:
            raise TypeError('Must generate the graph before trimming it.')

        deg_before = len(self.digr)

        for n in self.digr.successors_iter(self.home_node_label):
            # This should only have one item (.shadow), but just in case...
            self._check_eval(n)

        deg_diff = deg_before - len(self.digr)

        logging.info('Finished trimming %d unuseful nodes from the graph. Distinct nodes and their parents remain.'
                     % deg_diff)

    def _check_eval(self, node):
        """
        Recursively search successor nodes, evaluating their usefulness. A
        node is useful if:

        1. Any of its children are useful, or
        2. It was listed in fewer than the max number of files (it changed at
           some point)

        :param node: Label of the node to evaluate.
        :type node: str
        :return: True (useful, keep) or False (not useful, delete)
        :rtype: bool
        """
        # Check if this node has already been evaluated
        if self.digr.node[node]["eval"] is not None:
            logging.debug('Skipping eval of node: %s' % node)
            return self.digr.node[node]["eval"]

        # If this node is useful by itself, no need to check its children
        if len(self.digr.node[node]["src_files"]) < MAX_FILES:
            logging.debug('Skipping eval of child nodes of node: %s' % node)
            self.digr.node[node]["eval"] = True
            return True

        children_to_remove = []
        any_children_true = False
        for c in self.digr.successors_iter(node):
            e = self._check_eval(c)
            if not e:
                children_to_remove.append(c)
            any_children_true = any_children_true or e

        # Remove unneeded children
        self.digr.remove_nodes_from(children_to_remove)

        self.digr.node[node]["eval"] = any_children_true
        return any_children_true


def main():
    args = docopt(__doc__)

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
        diff.trim_unuseful()
        diff.show_graph('testfig.png')
    except:
        diff.deinit(False)
        raise
    diff.deinit()

if __name__ == '__main__':
    main()
