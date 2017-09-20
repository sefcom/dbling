#! /usr/bin/env python3
# *-* coding: utf-8 *-*
"""Gripper - Google Drive Activity Ripper

Usage: activity.py drive [options] (created | revised | comment) ...

Options:
 -c --cached    Use a cached version of the data, if available.
 -e EMAIL --email=EMAIL
                The email address to impersonate.
 --level=LEVEL  The granularity level of the resulting heat map [default: hr]

Note: If you start this script using ipython (recommended), you'll need to
invoke it like this:

    $ ipython3 activity.py -- [typical arguments]

The reason for this is that ipython interprets any options *before* the ``--``
as being meant for it.
"""

import plotly.plotly as py

from docopt import docopt

from gripper import get
from plot import heatmap


def main(**kwargs):

    levels = ('dy', 'sg', 'hr')
    if kwargs['--level'] not in levels:
        raise ValueError('Specified level must be one of {}'.format(levels))

    what = []
    if kwargs['created']:
        what.append('created')
    if kwargs['revised']:
        what.append('revisions')
    if kwargs['comment']:
        what.append('comments')

    if kwargs.get('drive'):
        api, title = 'drive', 'User Activity on Google Drive'
    else:
        # This should never happen since docopt validates commands for us
        raise ValueError('No known command given')

    drive = get(api, impersonated_user_email=kwargs['--email'])
    data = drive.activity(use_cached=kwargs['--cached'], what=what, level=kwargs['--level'])
    fig = heatmap(title=title, **data)

    plot_args = {
        'figure_or_data': fig,
        'filename': '{}-activity-heatmap'.format(api),
    }
    try:
        __IPYTHON__
    except NameError:
        url = py.plot(**plot_args)
        print('The plotted figure is now available at:\n{}'.format(url))
    else:
        py.iplot(**plot_args)


if __name__ == '__main__':
    _args = docopt(__doc__)
    main(**_args)
