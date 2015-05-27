#!/usr/bin/env python
"""
Requires packages:
graphviz-dev
python-pydot
"""

from bs4 import BeautifulSoup
from bs4.element import Tag
from colorama import init, Back, Fore  # BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE, RESET
from copy import deepcopy as copy
from hashlib import sha256
import json
import logging
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
INODE_ONLY = True


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


class ColorDiff(object):

    def __init__(self):
        self.digr = networkx.DiGraph()
        self.files = {}
        self.type_count = {}
        self.unknown_type_files = []

        # Initialize logging
        self._log_path = path.join(path.dirname(path.realpath(__file__)), '../log', "color_diff.log")
        with open(self._log_path, 'a') as fout:
            fout.write((' --  '*15)+'\n')
        log_format = '%(asctime)s %(levelname) 8s -- %(message)s'
        logging.basicConfig(filename=self._log_path, level=logging.DEBUG, format=log_format)
        logging.info('DFXML Color Diff initialized.')

    def deinit(self, clean=True):
        if clean:
            logging.info('Execution completed cleanly. Shutting down.')
        else:
            logging.warning('Unclean shutdown. Did not finish graphing the diffs.')
        logging.shutdown()  # Flush and close all handlers

    def show_graph(self, fig_filename):
        fileobject_types = ['encrypted files', 'encrypted directories', 'unencrypted files', 'unencrypted directories']

        # Generate positions for all the nodes, edges
        pos = networkx.pydot_layout(self.digr, prog='dot', root='home')

        for n in self.unknown_type_files:
            networkx.draw_networkx_nodes(self.digr, pos, nodelist=self.unknown_type_files,
                                         node_color='c', node_shape='s')

        # TODO: If this needs to support more than MAX_FILES==3, rewrite this
        for t, s in zip(range(4), ('h', 'd', 'o', '^')):
            # Iterate over the four types of files:
            # 0: encrypted_files
            # 1: encrypted_directories
            # 2: unencrypted_files
            # 3: unencrypted_directories
            logging.info('Drawing nodes for %s' % fileobject_types[t])

            # Only in file 1. Draw with shape s and color 'r'
            l = self.files[1][t] - self.files[2][t]# - self.files[3][t]
            networkx.draw_networkx_nodes(self.digr, pos, nodelist=l, node_color='r', node_shape=s)
            logging.debug('File 1 - File 2 - File 3')

            # Only in file 2. Draw with shape s and color 'b'
            l = self.files[2][t] - self.files[1][t]# - self.files[3][t]
            networkx.draw_networkx_nodes(self.digr, pos, nodelist=l, node_color='b', node_shape=s)
            logging.debug('File 2 - File 1 - File 3')

            # Only in file 3. Draw with shape s and color 'y'
            # l = self.files[3][t] - self.files[2][t] - self.files[1][t]
            # networkx.draw_networkx_nodes(self.digr, pos, nodelist=l, node_color='y', node_shape=s)
            # logging.debug('File 3 - File 2 - File 1')

            # In files 1 & 2. Draw with shape s and color 'purple'
            l = self.files[1][t] & self.files[2][t]# - self.files[3][t]
            networkx.draw_networkx_nodes(self.digr, pos, nodelist=l, node_color='purple', node_shape=s)
            logging.debug('File 1 & File 2')

            # In files 2 & 3. Draw with shape s and color 'g'
            # l = self.files[2][t] & self.files[3][t] - self.files[1][t]
            # networkx.draw_networkx_nodes(self.digr, pos, nodelist=l, node_color='g', node_shape=s)
            # logging.debug('File 2 & File 3 - File 1')

            # In files 1 & 3. Draw with shape s and color 'c'
            # l = self.files[1][t] & self.files[3][t] - self.files[2][t]
            # networkx.draw_networkx_nodes(self.digr, pos, nodelist=l, node_color='c', node_shape=s)
            # logging.debug('File 1 & File 3 - File 2')

            # In files 1 & 2 & 3. Draw with shape s and color '0.5'
            # l = self.files[1][t] & self.files[2][t] & self.files[3][t]
            # networkx.draw_networkx_nodes(self.digr, pos, nodelist=l, node_color='0.5', node_shape=s)
            # logging.debug('File 1 & File 2 & File 3')

        # Continue drawing here
        logging.info('Drawing edges, then saving the image.')
        networkx.draw_networkx_edges(self.digr, pos, alpha=0.8)

        plt.axis('off')
        plt.savefig(fig_filename)
        plt.show()

    def add_from_file(self, file_path):
        """
        Given the path to a DFXML file, add nodes and edges to the digraph
        representing its fileobjects.

        :param file_path: Path to the DFXML file from which to create the digraph.
        :type file_path: str
        :return: None
        :rtype: None
        """
        logging.info('Beginning import from file: %s' % file_path)
        with open(file_path) as xml_file:
            soup = BeautifulSoup(xml_file.read(), "xml")
        logging.info('DFXML converted to soup. Importing into a graph.')

        ex_pat1 = re.compile('/\.\.?$')
        ex_pat2 = re.compile('^/?home/\.shadow/(.+)')
        ex_pat3 = re.compile('^/?home$')
        ex_pat4 = re.compile('^/?home/\.shadow$')
        enc_pat5 = re.compile('/ECRYPTFS_FNEK_ENCRYPTED\.([^/]*)$')

        # Node info storage
        inode_paths = {}
        encrypted_files = []
        encrypted_directories = []
        unencrypted_files = []
        unencrypted_directories = []
        other_files = []
        duplicates = []
        self.type_count = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0}

        edges_to_add = []
        num_skipped_files = 0

        # Figure out which file this is: 1, 2, or 3
        file_num = None
        for i in range(1, MAX_FILES+1):
            try:
                self.files[i]
            except KeyError:
                file_num = i  # This is the one we want
                break

        for file_obj in soup.find_all('fileobject'):
            filename = file_obj.filename.string

            # Exclude all files that end in '/.' or '/..'
            if re.search(ex_pat1, filename):
                continue

            skip_add_edge = False
            if re.search(ex_pat3, filename):
                # Include 'home' and 'home/.shadow' so that other file objects can create edges with them
                skip_add_edge = True
            elif re.search(ex_pat4, filename):
                pass
            elif not re.search(ex_pat2, filename):
                # Exclude all files that don't start with 'home/.shadow/'
                continue

            # Get allocation status
            try:
                alloc = file_obj.alloc.string
            except AttributeError:
                try:
                    alloc = file_obj.unalloc.string
                except AttributeError:
                    logging.CRITICAL('File object has neither an alloc or unalloc tag: %s' % filename)
                    raise
                else:
                    alloc = str(1 - int(alloc))
            if alloc == '0':
                # TODO: Dr. Ahn wants these files to be included for some reason
                continue

            # Extract all pertinent information
            inode_num = None
            for c in file_obj.children:
                if isinstance(c, Tag) and c.name == 'inode':
                    inode_num = int(c.string)
                    break
            if inode_num is None:
                raise ValueError("Following file has no inode number: %s" % filename)

            basename = path.basename(filename)
            parent_obj = int(file_obj.parent_object.inode.string)
            meta_type = int(file_obj.meta_type.string)
            self.type_count[meta_type] += 1
            encrypted = bool(re.search(enc_pat5, filename))
            inode_paths[inode_num] = basename  # TODO: Set this to whatever the node label ends up being
            filename_id = sha256(filename).hexdigest()

            fs_offset = float('inf')
            for fs in file_obj.find_all('byte_run'):
                # Get the lowest offset of the file
                _off = int(fs['fs_offset'])
                if _off < fs_offset:
                    fs_offset = _off
            if fs_offset == float('inf'):
                fs_offset = '?'

            filesize = '?'
            try:
                # Try to use the DFXML-computed length first
                filesize = file_obj.filesize.string
            except AttributeError:
                # Iterate through the byte runs and sum their lengths
                _sum = 0
                for r in file_obj.find_all('byte_run'):
                    _sum += int(r['len'])
                if _sum > 0:
                    filesize = _sum

            attrs = {"inode": inode_num,
                     "parent_inode": parent_obj,
                     # "filename": filename,
                     "filename_id": filename_id,
                     "filename_end": filename[-13:],
                     "name_type": file_obj.name_type.string,
                     "type": meta_type,
                     "alloc": alloc,
                     "fs_offset": fs_offset,
                     "filesize": filesize,
                     }


            # Stubborn parameters
            for k, o in (("size", file_obj.filesize),
                         ("mode", file_obj.mode),
                         ("used", file_obj.used),
                         ("uid", file_obj.uid),
                         ("gid", file_obj.gid),
                         ("nlink", file_obj.nlink),
                         ("mtime", file_obj.mtime),
                         ("ctime", file_obj.ctime),
                         ("atime", file_obj.atime),
                         ("crtime", file_obj.crtime)):
                try:
                    attrs[k] = o.string
                except AttributeError:
                    attrs[k] = '?'

            # Store information about the node
            if INODE_ONLY:
                _id = inode_num
            else:
                _id = basename

            if meta_type == FILE:
                if encrypted:
                    encrypted_files.append(_id)
                else:
                    unencrypted_files.append(_id)
            elif meta_type == DIRECTORY:
                if encrypted:
                    encrypted_directories.append(_id)
                else:
                    unencrypted_directories.append(_id)
            else:
                other_files.append(_id)

            # Make sure we don't try to double-add a node in the digraph
            if self.digr.has_node(_id):
                num_skipped_files += 1
                if file_num == 1:
                    # Save information on the duplicates for printing later
                    duplicates.append((self.digr.node[_id], attrs))
                continue

            # Add node and edge to the graph
            self.digr.add_node(_id, attrs)
            if not skip_add_edge:
                edges_to_add.append((parent_obj, _id))

        logging.info("Done importing. Number of skipped files: %d" % num_skipped_files)
        logging.info("File count by type: %s" % self.type_count)
        type_sum = 0
        for i in self.type_count:
            type_sum += self.type_count[i]
        logging.info("Total file objects: %d" % type_sum)

        if file_num == 1:
            print("\nDuplicates:"),
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
            break_str = ('  -- ' * ((len(header) / 5) + 1))[:len(header)]
            header = make_yellow(make_black(header, 0))
            line_count = 0
            for x, y in duplicates:
                print('')
                if not line_count % 10:
                    print(header)
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

                print(dstring % tuple(x_fields))
                print(dstring % tuple(y_fields))
                print(make_green(break_str, 0)),
            raise KeyboardInterrupt

        for u, v in edges_to_add:
            if INODE_ONLY:
                self.digr.add_edge(u, v)
            else:
                self.digr.add_edge(inode_paths[u], v)

        self.files[file_num] = (set(encrypted_files),
                                set(encrypted_directories),
                                set(unencrypted_files),
                                set(unencrypted_directories))
        self.unknown_type_files += other_files


def main():
    with open(path.join(path.dirname(path.realpath(__file__)), 'dbling_conf.json')) as fin:
        img_dir = json.load(fin)['img_dir']
    imgs = os.listdir(img_dir)
    imgs.sort(reverse=True)
    to_compare = []
    dfxml_ext = re.compile('\.df\.xml$')

    diff = ColorDiff()
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
    for i in to_compare:
        try:
            diff.add_from_file(i)
        except:
            diff.deinit(False)
            raise

    try:
        diff.show_graph('testfig.png')
    except:
        diff.deinit(False)
        raise
    diff.deinit()

if __name__ == '__main__':
    main()
