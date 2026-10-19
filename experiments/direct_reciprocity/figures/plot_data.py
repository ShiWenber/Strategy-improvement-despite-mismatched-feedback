"""Data-derived numeric limits and interval geometry shared by the renderers."""
import numpy as np
from matplotlib.ticker import MaxNLocator, ScalarFormatter


def finite_values(values):
    array = np.asarray(values, dtype=float).ravel()
    if not array.size or not np.isfinite(array).all():
        raise ValueError('Plot values must be nonempty and finite')
    return array


def interval_values(rows, key='ci95'):
    values = []
    for row in rows:
        low, high = finite_values(row[key])
        if low > high:
            raise ValueError('Interval endpoints are reversed')
        values.extend((row['mean'], low, high))
    return finite_values(values)


def data_limits(values, *, include_zero=False, padding=.08, headroom=0., nonnegative=False):
    array = finite_values(values)
    low, high = float(array.min()), float(array.max())
    if nonnegative and low < 0:
        raise ValueError('Negative values in a nonnegative measurement')
    if include_zero or nonnegative:
        low, high = min(0., low), max(0., high)
    span = high - low or max(abs(low), abs(high)) or 1.
    return (0. if nonnegative else low - span * padding,
            high + span * (padding + headroom))


def fit_axis(ax, values, axis='x', *, nbins=4, integer=False, **options):
    limits = data_limits(values, **options)
    getattr(ax, 'set_' + axis + 'lim')(*limits)
    target = getattr(ax, axis + 'axis')
    target.set_major_locator(MaxNLocator(nbins=nbins, integer=integer))
    formatter = ScalarFormatter(useMathText=True)
    formatter.set_useOffset(False)
    target.set_major_formatter(formatter)
    return limits


def draw_intervals(ax, positions, low, high, *, axis='x', **style):
    low, high = np.broadcast_arrays(np.asarray(low, dtype=float), np.asarray(high, dtype=float))
    finite_values([low, high])
    if np.any(low > high):
        raise ValueError('Interval endpoints are reversed')
    midpoint, half_width = (low + high) / 2, (high - low) / 2
    if axis == 'x':
        return ax.errorbar(midpoint, positions, xerr=half_width, fmt='none', **style)
    return ax.errorbar(positions, midpoint, yerr=half_width, fmt='none', **style)
