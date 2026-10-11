"""Shared embedding wire/store contract, independent of model loaders."""
import math
from ai_profiles import DEFAULT_PROFILE

def normalized(vector,dimension=DEFAULT_PROFILE.dimension):
    if len(vector)!=dimension or any(not math.isfinite(x) for x in vector):
        raise ValueError('Invalid embedding')
    norm=math.sqrt(sum(x*x for x in vector))
    if norm<1e-12:
        raise ValueError('Zero embedding')
    return [x/norm for x in vector]
