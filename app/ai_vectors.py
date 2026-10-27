"""Shared embedding wire/store contract, independent of model loaders."""
import math
from operator import mul
from ai_profiles import DEFAULT_PROFILE


def dot(left,right):
    """Dot product of validated vectors, preserving Python sum/product order.

    map avoids the per-element Python generator frame. Do not divide or round
    here: existing search contracts retain their own normalization and scores.
    """
    return sum(map(mul,left,right))

def normalized(vector,dimension=DEFAULT_PROFILE.dimension):
    if len(vector)!=dimension or any(not math.isfinite(x) for x in vector):
        raise ValueError('Invalid embedding')
    norm=math.sqrt(sum(x*x for x in vector))
    if norm<1e-12:
        raise ValueError('Zero embedding')
    return [x/norm for x in vector]
