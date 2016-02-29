#!/usr/bin/env python3
"""
The case study script for the DFRWS paper.

Usage: case_study.py [options] -d DFXML_FILE
       case_study.py [options] -m MOUNT_POINT

Options:
 -v   Verbose mode. Changes logging mode from INFO to DEBUG.
 -g   Show graph before searching for matches.
"""
import logging
from docopt import docopt
from graph_diff import FilesDiff, init_logging
from merl import Merl


def go(start, mounted=False, verbose=False, show_graph=False):
    init_logging(verbose=verbose)
    graph = FilesDiff()
    if mounted:
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

        # Pick a vertex, any vertex
        for start in sub_graph.vertices():
            break

        sg_vertices = [start]

        # Get the list of parent vertices all the way back, add it to the list of subgraph vertices
        sg_vertices += get_ancestors(start)

        # Get the list of child vertices all the way down, add it to the list of subgraph vertices
        sg_vertices += get_descendants(start)

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

    return candidates


def get_ancestors(node):
    """
    Return a recursively-discovered list of the vertex's in-neighbors.

    :param node: The starting vertex
    :type node: graph_tool.Vertex
    :return: The list of all ancestor vertices of the starting vertex.
    :rtype: list
    """
    l = []
    for v in node.in_neighbours():
        l.append(v)
        l += get_ancestors(v)
    return l


def get_descendants(node):
    """
    Return a recursively-discovered list of the vertex's out-neighbors.

    :param node: The starting vertex.
    :type node: graph_tool.Vertex
    :return: The list of all descendant vertices of the starting vertex.
    :rtype: list
    """
    l = []
    for v in node.out_neighbours():
        l.append(v)
        l += get_descendants(v)
    return l


if __name__ == '__main__':
    args = docopt(__doc__)
    if args['-d']:
        start = args['DFXML_FILE']
    elif args['-m']:
        start = args['MOUNT_POINT']

    go(start, args['-m'], args['-v'])
