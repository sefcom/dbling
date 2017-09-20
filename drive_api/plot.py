# -*- coding: utf-8 -*-

import plotly.graph_objs as go

#: Color scale used by the heat map
HEATMAP_COLORS = ('#e7f0fa', '#c9e2f6', '#95cbee', '#0099dc', '#4ab04a',
                  '#ffd73e', '#eec73a', '#e29421', '#e29421', '#f05336', '#ce472e')
#: Changes how quickly the colors go to the maximum
STOP_FACTOR = 80


def stop(i):
    """Return the ``i``th color stop.

    In color gradients, the point where a defined color is (as opposed to in
    between the defined colors, where the colors are "graded") is called a
    "stop". This Python function defines an exponential math function that
    returns floating point values, in the range of ``0`` to ``1``, that define
    where the gradient stops should occur. In the :func:`heatmap` function,
    these values will be used to determine the color of each cell based on the
    normalized values of the ``z`` parameters.

    The number of stops is determined by the number of colors defined in
    :data:`HEATMAP_COLORS`. The math function used is below. In it,
    ``m = STOP_FACTOR`` and ``n = len(HEATMAP_COLORS)``.

    .. math::

       (m^(i/(n - 1)) - 1) / (m - 1)

    :param int i: The current stop number. Must be a value between 0 and
        ``len(HEATMAP_COLORS) - 1``, i.e. ``[0, n)``.
    :return: Where the ``i``th color stop should occur. Will always be a value
        between 0 and 1.
    :rtype: float
    :raise ValueError: When ``i`` isn't between 0 and
        ``len(HEATMAP_COLORS) -1``.
    """
    if 0 > i or i >= len(HEATMAP_COLORS):
        raise ValueError
    return (STOP_FACTOR ** (i / (len(HEATMAP_COLORS) - 1)) - 1) / (STOP_FACTOR - 1)


def heatmap(x, y, z, title=''):
    """Create and return a heat map figure object for the given data.

    :param x: Data for the x-axis.
    :type x: list or tuple
    :param y: Data for the y-axis.
    :type y: list or tuple
    :param z: Data for the z-axis.
    :type z: list or tuple
    :param str title: A title for the figure.
    :return: The object with the data's graph. With this object you can then
        call its :meth:`~plotly.graph_objs.Figure.iplot` method to show the
        graph.
    :rtype: plotly.graph_objs.Figure
    """
    data = [go.Heatmap(z=z, x=x, y=y,
                       colorscale=[[stop(i), j] for i, j in enumerate(HEATMAP_COLORS)])
            ]

    layout = go.Layout(
        title=title,
        xaxis=dict(
            rangeselector=dict(
                buttons=list([
                    dict(count=1,
                         label='1m',
                         step='month',
                         stepmode='backward'),
                    dict(count=6,
                         label='6m',
                         step='month',
                         stepmode='backward'),
                    dict(count=1,
                         label='YTD',
                         step='year',
                         stepmode='todate'),
                    dict(count=1,
                         label='1y',
                         step='year',
                         stepmode='backward'),
                    dict(step='all')
                ])
            ),
            rangeslider=dict(),
            type='date'
        ),
        yaxis=dict(ticks='')
    )

    return go.Figure(data=data, layout=layout)
