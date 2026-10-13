"""Display-only similarity boundaries; never a character/correctness classifier."""
import math,statistics

def boundary(ranked,score_kind,requested=None):
    if requested is not None and (type(requested) not in (int,float) or not math.isfinite(requested) or not -1<=requested<=1):
        raise ValueError('Invalid similarity boundary')
    if score_kind!='cosine':
        if requested is not None:raise ValueError('Similarity boundary requires cosine scores')
        return None
    if requested is not None:return float(requested)
    # Suggest a boundary only for a conspicuous gap in the leading results.
    # This heuristic is uncalibrated and conveys relative similarity only.
    scores=[pair[1] for pair in ranked[:32]]
    gaps=[a-b for a,b in zip(scores,scores[1:])]
    positive=[gap for gap in gaps if gap>1e-6]
    if not positive:return None
    largest=max(gaps);i=gaps.index(largest)
    if largest<0.03 or largest<4*statistics.median(gaps):return None
    return (scores[i]+scores[i+1])/2
