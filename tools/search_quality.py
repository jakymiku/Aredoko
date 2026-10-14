"""Fixed-fixture retrieval metrics. Never use ranking scores as confidence."""
import math

def metrics(ranked, relevance, cutoff=5):
    if type(cutoff) is not int or cutoff<1:raise ValueError('Positive cutoff required')
    if len(set(ranked))!=len(ranked):raise ValueError('Duplicate ranked keys')
    if any(type(grade) is not int or not 1<=grade<=2 for grade in relevance.values()):
        raise ValueError('Relevance grades must be 1 or 2')
    if not relevance:return None
    hits=[index for index,key in enumerate(ranked,1) if key in relevance]
    top=ranked[:cutoff]
    gains=lambda grades:sum((2**grade-1)/math.log2(index+2) for index,grade in enumerate(grades))
    ideal=gains(sorted(relevance.values(),reverse=True)[:cutoff])
    dcg=gains([relevance.get(key,0) for key in top])
    return {'hit_at_1':float(bool(ranked) and ranked[0] in relevance),
            'best_grade_at_1':float(bool(ranked) and relevance.get(ranked[0],0)==max(relevance.values())),
            'recall_at_5':sum(key in relevance for key in top)/len(relevance),
            # Precision over the actually returned top list (up to cutoff),
            # not five padded slots. Empty output has precision zero.
            'precision_at_5':sum(key in relevance for key in top)/len(top) if top else 0.0,
            'mrr':1/hits[0] if hits else 0.0,'ndcg_at_5':dcg/ideal}

def summary(rows):
    # One mean per source/filter/group. Correlated variants are not independent queries.
    grouped={}
    for row in rows:
        key=(row['group'],row['source'],row['filter'])
        grouped.setdefault(key,[]).append(row)
    result=[]
    for (group,source,variant),entries in sorted(grouped.items()):
        measured=[entry['metrics'] for entry in entries if entry['metrics'] is not None]
        result.append({'group':group,'source':source,'filter':variant,'cases':len(entries),
            'scored_cases':len(measured),'means':{key:sum(m[key] for m in measured)/len(measured)
            for key in measured[0]} if measured else None})
    return result
