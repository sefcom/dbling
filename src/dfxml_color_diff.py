#!/usr/bin/env python

from bs4 import BeautifulSoup
import json
from matplotlib import pyplot as plt
import networkx
import os
from os import path
import re


FILE = 1
DIRECTORY = 2
DT_DIR = 4
DT_REG = 8
MAX_FILES = 3


class ColorDiff(object):

    def __init__(self):
        self.digr = networkx.DiGraph()
        self.files = {}

    def show_graph(self, fig_filename):
        # TODO: If this needs to support more than MAX_FILES==3, rewrite this
        for t, s in zip(range(4), ('s', 'd', 'o', '^')):
            # Iterate over the four types of files:
            # 0: encrypted_files
            # 1: encrypted_directories
            # 2: unencrypted_files
            # 3: unencrypted_directories

            # Only in file 1. Draw with shape s and color 'r'
            l = self.files[1][t] - self.files[2][t] - self.files[3][t]
            networkx.draw_networkx_nodes(self.digr, {}, nodelist=l, node_color='r', node_shape=s)

            # Only in file 2. Draw with shape s and color 'b'
            l = self.files[2][t] - self.files[1][t] - self.files[3][t]
            networkx.draw_networkx_nodes(self.digr, {}, nodelist=l, node_color='b', node_shape=s)

            # Only in file 3. Draw with shape s and color 'y'
            l = self.files[3][t] - self.files[2][t] - self.files[1][t]
            networkx.draw_networkx_nodes(self.digr, {}, nodelist=l, node_color='y', node_shape=s)

            # In files 1 & 2. Draw with shape s and color 'purple'
            l = self.files[1][t] & self.files[2][t] - self.files[3][t]
            networkx.draw_networkx_nodes(self.digr, {}, nodelist=l, node_color='purple', node_shape=s)

            # In files 2 & 3. Draw with shape s and color 'g'
            l = self.files[2][t] & self.files[3][t] - self.files[1][t]
            networkx.draw_networkx_nodes(self.digr, {}, nodelist=l, node_color='g', node_shape=s)

            # In files 1 & 3. Draw with shape s and color 'c'
            l = self.files[1][t] & self.files[3][t] - self.files[2][t]
            networkx.draw_networkx_nodes(self.digr, {}, nodelist=l, node_color='c', node_shape=s)

            # In files 1 & 2 & 3. Draw with shape s and color '0.5'
            l = self.files[1][t] & self.files[2][t] & self.files[3][t]
            networkx.draw_networkx_nodes(self.digr, {}, nodelist=l, node_color='0.5', node_shape=s)

        # Continue drawing here
        networkx.draw_networkx_edges(self.digr, {}, alpha=0.8)

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
        with open(file_path) as xml_file:
            soup = BeautifulSoup(xml_file.read(), "xml")

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

        edges_to_add = []
        num_skipped_files = 0
        max_files = 50
        num_files = 0

        for file_obj in soup.find_all('fileobject'):
            filename = file_obj.filename.string

            # Exclude all files that end in '/.' or '/..'
            if re.search(ex_pat1, filename):
                continue

            if re.search(ex_pat3, filename) or re.search(ex_pat4, filename):
                # Include 'home' and 'home/.shadow' so that other file objects can create edges with them
                pass
            elif not re.search(ex_pat2, filename):
                # Exclude all files that don't start with 'home/.shadow/'
                continue

            # Extract all pertinent information
            basename = path.basename(filename)
            parent_obj = int(file_obj.parent_object.inode.string)
            inode_num = int(file_obj.inode.string)  # TODO: Verify this pulls the right value
            meta_type = int(file_obj.meta_type.string)
            encrypted = bool(re.search(enc_pat5, filename))
            # if meta_type == DIRECTORY:
            inode_paths[inode_num] = basename

            # Store information about the node
            if encrypted:
                if meta_type == FILE:
                    encrypted_files.append(basename)
                elif meta_type == DIRECTORY:
                    encrypted_directories.append(basename)
            else:
                if meta_type == FILE:
                    unencrypted_files.append(basename)
                elif meta_type == DIRECTORY:
                    unencrypted_directories.append(basename)

            # TODO: Remove this after debugging
            num_files += 1
            if num_files > max_files:
                break

            # Make sure we don't try to double-add a node in the digraph
            # TODO: Maybe store the inode number and compare before rejecting?
            if self.digr.has_node(basename):
                num_skipped_files += 1
                continue

            self.digr.add_node(basename)
            edges_to_add.append((parent_obj, basename))

        print("Number of skipped files: %d" % num_skipped_files)

        for u, v in edges_to_add:
            self.digr.add_edge(inode_paths[u], v)

        # Figure out which file this was: 1, 2, or 3
        num = None
        for i in range(1, MAX_FILES+1):
            try:
                self.files[i]
            except KeyError:
                num = i  # This is the one we want
                break

        self.files[num] = (set(encrypted_files),
                           set(encrypted_directories),
                           set(unencrypted_files),
                           set(unencrypted_directories))


def main():
    with open(path.join(path.dirname(path.realpath(__file__)), 'dbling_conf.json')) as fin:
        img_dir = json.load(fin)['img_dir']
    imgs = os.listdir(img_dir)
    imgs.sort(reverse=True)
    to_compare = []

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
        to_compare.append(path.join(img_dir, i))
        if len(to_compare) == MAX_FILES:
            break

    to_compare.sort()
    for i in to_compare:
        diff.add_from_file(i)

    diff.show_graph('testfig.png')

if __name__ == '__main__':
    main()
