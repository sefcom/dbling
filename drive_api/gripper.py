#! /usr/bin/env python3
# *-* coding: utf-8 *-*
"""Gripper - Google Drive Activity Ripper

Usage: gripper.py drive [options] (created | revised | comment) ...
       gripper.py reports [options]

Options:
 -c --cached    Use a cached version of the data, if available.
 -e EMAIL --email=EMAIL
                The email address of a user to impersonate. This requires
                domain-wide delegation to be activated. See
                https://developers.google.com/admin-sdk/reports/v1/guides/delegation
                for instructions.
 --level=LEVEL  The granularity level of the resulting heat map [default: hr]
 --start=START -s START
                The earliest data to collect. Can be any kind of date string,
                as long as it is unambiguous (e.g. "2017"). It can even be
                slang, such as "a year ago". Be aware, however, that only the
                *day* of the date will be used, meaning time information will
                be discarded.
 --end=END -e END
                The latest data to collect. Same format rules apply for this
                as for --start.
 --tz=TIMEZONE  The timezone to convert all timestamps to before compiling.
                This should be a standard timezone name. For reference, the
                list that the timezone will be compared against is available
                at https://github.com/newvem/pytz/blob/master/pytz/__init__.py.
                If omitted, the local timezone of the computer will be used.

Note: If you start this script using ipython (recommended), you'll need to
invoke it like this:

    $ ipython3 gripper.py -- [typical arguments]

The reason for this is that ipython interprets any options *before* the ``--``
as being meant for it.
"""

import plotly.plotly as py

from docopt import docopt

from api_connectors import get_api
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
    elif kwargs.get('reports'):
        api, title = 'reports', 'Something Awesome'
    else:
        # This should never happen since docopt validates commands for us
        raise ValueError('No known command given')

    args = dict(
        api=api,
        impersonated_user_email=kwargs['--email'],
        start=kwargs['--start'],
        end=kwargs['--end'],
        timezone=kwargs['--tz'],
    )
    api_obj = get_api(**args)
    data = api_obj.activity(use_cached=kwargs['--cached'], what=what, level=kwargs['--level'])
    fig = heatmap(title=title, **data)

    plot_args = {
        'figure_or_data': fig,
        'filename': '{}-activity-heatmap'.format(api),
    }
    try:
        __IPYTHON__
    except NameError:
        url = py.plot(**plot_args)
        print('The plotted figure is now available at:\n{}\n'.format(url))
    else:
        py.iplot(**plot_args)


if __name__ == '__main__':
    _args = docopt(__doc__)
    # The Google API library uses a library that uses argparse, which parses argv as part of its attempt to
    # get valid OAuth credentials. So, to avoid errors created by argparse attempting to interpret arguments
    # meant for this script, we have to strip all arguments away except the invoked script.
    import sys
    sys.argv = sys.argv[:1]
    main(**_args)
