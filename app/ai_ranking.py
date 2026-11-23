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
        modalities=sorted({mode for modes in scores.values() for mode in modes})
        pools={mode:[modes[mode] for modes in scores.values() if mode in modes] for mode in modalities}
        # Half the cosine span avoids overflow for finite extreme inputs; the
        # common factor cancels. No fitted threshold or model-specific scale.
        spans={mode:max(values)/2-min(values)/2 for mode,values in pools.items()}
        largest=max(spans.values())
        informative=(len(modalities)>1 and all(len(values)>1 for values in pools.values()) and largest>0)
        weights={mode:spans[mode]/largest if informative else 1.0 for mode in modalities}
        for mode in modalities:
            ranked=sorted(((item,modes[mode]) for item,modes in scores.items() if mode in modes),key=lambda x:(-x[1],x[0]))
            first=0
            while first<len(ranked):
                last=first+1
                while last<len(ranked) and ranked[last][1]==ranked[first][1]:last+=1
                # Average tied positions: IDs must not manufacture a preference.
                position=((first+1)+last)/2
                for item,_ in ranked[first:last]:combined[item]+=weights[mode]/(RRF_K+position)
                first=last
        # Normalize only by the item's available evidence, preserving text-only
        # candidates. Constant-only evidence cannot outrank a discriminating
        # mode, but remains in the result set (no rejection threshold).
        denominators={item:sum(weights[mode] for mode in scores[item]) for item in scores}
        combined={item:value/denominators[item] if denominators[item]>0 else 0.0
                  for item,value in combined.items()}
    return sorted(combined.items(),key=lambda x:(-x[1],x[0]))
