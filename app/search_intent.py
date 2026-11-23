"""Decision interface: suggestions only; never changes search/filter requests."""
import math
from library_index import TYPES

MAX_QUERY=300
INTENTS=('cover','text','mixed')
KINDS=('book','image','audio','video','archive','any')
from intent_questions import get_questions
QUESTIONS=get_questions('v1')

def validate_query(query):
    if not isinstance(query,str) or len(query)>MAX_QUERY or '\x00' in query:
        raise ValueError('Query must be text of at most 300 characters')
    return query.strip()

def validate_decision(result,questions=QUESTIONS):
    if not isinstance(result,dict) or not isinstance(result.get('answers'),dict):
        raise ValueError('Missing decision answers')
    usage=result.get('usage',{})
    if not isinstance(usage,dict): raise ValueError('Invalid decision usage')
    if usage.get('truncated') or usage.get('truncated_questions'):
        raise ValueError('Truncated decision input')
    answer={}
    for key in ('intent','kind'):
        labels=tuple(questions[key]['criteria'])
        row=result['answers'].get(key)
        if not isinstance(row,dict) or row.get('type')!='choice' or row.get('choice') not in labels:
            raise ValueError('Invalid decision choice')
        probabilities=row.get('probabilities')
        if not isinstance(probabilities,dict) or set(probabilities)!=set(labels):
            raise ValueError('Invalid decision probabilities')
        if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v)
               or not 0<=v<=1 for v in probabilities.values()):
            raise ValueError('Invalid decision probability')
        if abs(sum(probabilities.values())-1)>0.002: raise ValueError('Invalid probability total')
        maximum=max(probabilities.values())
        if probabilities[row['choice']]<maximum: raise ValueError('Choice disagrees with probability')
        # Scores are recorded as uncalibrated evidence, never as reliability or an acceptance gate.
        answer[key]={'choice':row['choice'],'probabilities':probabilities}
    stability=result.get('order_consistent')
    if stability is not None:
        if not isinstance(stability,dict) or set(stability)!={'intent','kind'} or any(type(v) is not bool for v in stability.values()):
            raise ValueError('Invalid order consistency')
        answer['order_consistent']=stability
    return answer

class IntentUnavailable(RuntimeError): pass

class SearchIntent:
    def __init__(self,provider=None):self.provider=provider
    def status(self):
        return {'enabled':self.provider is not None,
                'available':bool(self.provider and self.provider.available),
                'device':self.provider.device if self.provider else '',
                'experimental':True,'applies_automatically':False,
                'question_set':getattr(self.provider,'question_set',None),
                'order_check':getattr(self.provider,'check_order',False)}
    def suggest(self,query,source='all',kind=''):
        query=validate_query(query)
        if source not in ('all','text','cover') or kind not in ('',)+tuple(TYPES):
            raise ValueError('Invalid manual search setting')
        response={'experimental':True,'applies_automatically':False,
                  'requested':{'source':source,'kind':kind},'suggestion':None}
        if not query:return {**response,'state':'empty'}
        if not self.provider:return {**response,'state':'disabled'}
        try:
            decision=validate_decision(self.provider.decide(query),getattr(self.provider,'questions',QUESTIONS))
        except (IntentUnavailable,ValueError,TypeError,KeyError,RuntimeError,OSError):
            return {**response,'state':'unavailable'}
        intent=decision['intent']['choice'];suggested_kind=decision['kind']['choice']
        stable=decision.get('order_consistent',{})
        abstained=[]
        if stable.get('intent') is False:intent='mixed';abstained.append('intent')
        if stable.get('kind') is False:suggested_kind='any';abstained.append('kind')
        reasons={key:'option-order-disagreement' for key in abstained}
        # Until these contents have encoders, they have no cover vectors. Contradictory
        # model heads must not suggest a search with no usable candidates. This changes
        # only the suggestion, never the caller's explicit kind or mode.
        if intent=='cover' and suggested_kind in ('audio','video','material'):
            intent='mixed';abstained.append('intent');reasons['intent']='no-cover-for-suggested-kind'
        return {**response,'state':'suggested','suggestion':{
            'intent':intent,'source':{'cover':'cover','text':'text','mixed':'all'}[intent],
            'kind':suggested_kind,'scores':decision,'scores_calibrated':False,
            'abstained':abstained,'abstention_reasons':reasons,'order_checked':bool(stable)}}
    def close(self):
        if self.provider:self.provider.close()
