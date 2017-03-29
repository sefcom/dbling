#!/usr/bin/env python3
"""
The case study script for the DFRWS paper.

Usage: case_study.py [options] -d DFXML_FILE
       case_study.py [options] -m MOUNT_POINT

Options:
 -v   Verbose mode. Changes logging mode from INFO to DEBUG.
 -g   Show graph before searching for matches.
 -o MERL   Output results to the file MERL.
"""
import logging
from os import geteuid, seteuid

from docopt import docopt

from graph_diff import FilesDiff, init_logging
from merl import Merl
from graph_tool.topology import shortest_distance


MAX_DIST = 2147483647  # Assumes the distance PropertyMap will be of type int32


def go(start, mounted=False, verbose=False, show_graph=False, output_file=None):
    init_logging(verbose=verbose)
    graph = FilesDiff()
    if mounted:
        try:
            euid = geteuid()
            if euid != 0:
                seteuid(0)
        except PermissionError:
            msg = 'Must have root privileges to read from a mount point.'
            logging.critical(msg)
            print('\n%s\n' % msg)
            raise
        graph.add_from_mount(start)
    else:
        graph.add_from_file(start)
    graph.trim_unuseful(True)
    if show_graph:
        graph.show_graph()
    # return
    candidates = extract_candidates(graph.graph_copy())
    # for c in candidates:
    #     graph.show_graph(c)

    logging.info('Searching the DB for matches for each candidate graph. (%d)' % len(candidates))
    merl = Merl()
    merl.output_file = output_file
    merl.match_candidates(candidates)
    # TODO: Save XML to file

    merl.close_db()

    logging.info('Search complete. Exiting.')


def extract_candidates(orig_graph):
    """
    Return a list of graph objects, each a candidate graph.

    :param orig_graph: The original graph made from the DFXML.
    :type orig_graph: graph_tool.Graph
    :return: List of candidate graph objects.
    :rtype: list
    """
    candidates = []
    while True:
        # Stop iterating when we've emptied the original graph
        if orig_graph.num_vertices() == 0:
            break
        sub_graph = orig_graph.copy()

        sg_vertices = get_subtree_vertices(sub_graph)

        # Remove all vertices in the subgraph from the original graph
        rm_list = []
        for v in orig_graph.vertices():
            if v in sg_vertices:
                rm_list.append(v)
        orig_graph.remove_vertex(rm_list)

        # Remove all vertices not in the list
        rm_list = []
        for v in sub_graph.vertices():
            if v not in sg_vertices:
                rm_list.append(v)
        sub_graph.remove_vertex(rm_list)

        # Add the subgraph to the list of candidates
        if sub_graph.num_vertices():
            # Must have at least one vertex to be of interest to us
            candidates.append(sub_graph)
            if not len(candidates) % 5:
                logging.debug('Extracted candidate graph %d' % len(candidates))

    return candidates


def get_subtree_vertices(g):
    """
    Return a list of all vertices connected to node.

    :param g: The graph from which to extract a subgraph.
    :type g: graph_tool.Graph
    :return: The list of all vertices in a subgraph of g.
    :rtype: list
    """

    # Get the shortest distance from the first vertex in the graph and everything else
    dist = shortest_distance(g, g.vertex(0), directed=False)

    l = []
    for v, i in zip(dist.a, range(len(dist.a))):
        # If the calculated distance is the max, assume it is infinite (not reachable), i.e. not part of the same
        # subgraph.
        if v < MAX_DIST:
            l.append(g.vertex(i))

    return l


if __name__ == '__main__':
    args = docopt(__doc__)
    _start = None
    if args['-d']:
        _start = args['DFXML_FILE']
    elif args['-m']:
        _start = args['MOUNT_POINT']

    if args['-o'] is not None:
        with open(args['-o'], 'w') as fout:
            go(_start, args['-m'], args['-v'], args['-g'], output_file=fout)
    else:
        go(_start, args['-m'], args['-v'], args['-g'])
