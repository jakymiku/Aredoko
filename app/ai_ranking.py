"""Explicit fusion policies; vector storage/model identities are unchanged."""
import math

POLICIES=('max','mean-rrf')
RRF_K=60

def fuse_modalities(scores,policy='max'):
    if policy not in POLICIES:raise ValueError('Unknown ranking policy')
    if not scores:return []
    if any(not modes or any(not math.isfinite(v) for v in modes.values()) for modes in scores.values()):
        raise ValueError('Invalid modality scores')
    if policy=='max':combined={item:max(modes.values()) for item,modes in scores.items()}
    else:
        combined={item:0.0 for item in scores}
        modalities={mode for modes in scores.values() for mode in modes}
        for mode in modalities:
            ranked=sorted(((item,modes[mode]) for item,modes in scores.items() if mode in modes),key=lambda x:(-x[1],x[0]))
            first=0
            while first<len(ranked):
                last=first+1
                while last<len(ranked) and ranked[last][1]==ranked[first][1]:last+=1
                # Average tied positions: IDs must not manufacture a preference.
                position=((first+1)+last)/2
                for item,_ in ranked[first:last]:combined[item]+=1/(RRF_K+position)
                first=last
        # Missing covers must not halve evidence or make dual-modality items win
        # merely because they have twice as many vectors.
        combined={item:value/len(scores[item]) for item,value in combined.items()}
    return sorted(combined.items(),key=lambda x:(-x[1],x[0]))
