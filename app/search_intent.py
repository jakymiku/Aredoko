"""Decision interface: suggestions only; never changes search/filter requests."""
import math
from library_index import TYPES

MAX_QUERY=300
INTENTS=('cover','text','mixed')
KINDS=('book','image','audio','video','archive','any')
QUESTIONS={
    'intent':{'type':'choice','instructions':
        'この検索文では、主に何を手がかりとしてファイルを探していますか？曖昧・複合・内容の連想はmixed。',
        'criteria':{
            'cover':'画像や表紙の見た目、色、構図、描かれた人物や物を手がかりに探す',
            'text':'ファイル名、作品タイトル、作者名、タグなど文字情報を手がかりに探す',
            'mixed':'内容や雰囲気を連想する検索、見た目と文字の複合検索、手がかりが不明'}},
    'kind':{'type':'choice','instructions':
        '検索文で明示的に探しているファイルの種類を選んでください。種類が不明または複数ならany。',
        'criteria':{
            'book':'本、同人誌、漫画など読書する作品',
            'image':'画像、イラスト、写真、壁紙など一枚の画像',
            'audio':'音楽、曲、音声、効果音',
            'video':'動画、映像、ムービー',
            'archive':'本と明示されていない圧縮ファイルや素材パック',
            'any':'種類を指定していない、曖昧、または複数の種類'}}}

def validate_query(query):
    if not isinstance(query,str) or len(query)>MAX_QUERY or '\x00' in query:
        raise ValueError('Query must be text of at most 300 characters')
    return query.strip()

def validate_decision(result):
    if not isinstance(result,dict) or not isinstance(result.get('answers'),dict):
        raise ValueError('Missing decision answers')
    usage=result.get('usage',{})
    if not isinstance(usage,dict): raise ValueError('Invalid decision usage')
    if usage.get('truncated') or usage.get('truncated_questions'):
        raise ValueError('Truncated decision input')
    answer={}
    for key,labels in (('intent',INTENTS),('kind',KINDS)):
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
    return answer

class IntentUnavailable(RuntimeError): pass

class SearchIntent:
    def __init__(self,provider=None):self.provider=provider
    def status(self):
        return {'enabled':self.provider is not None,
                'available':bool(self.provider and self.provider.available),
                'device':self.provider.device if self.provider else '',
                'experimental':True,'applies_automatically':False}
    def suggest(self,query,source='all',kind=''):
        query=validate_query(query)
        if source not in ('all','text','cover') or kind not in ('',)+tuple(TYPES):
            raise ValueError('Invalid manual search setting')
        response={'experimental':True,'applies_automatically':False,
                  'requested':{'source':source,'kind':kind},'suggestion':None}
        if not query:return {**response,'state':'empty'}
        if not self.provider:return {**response,'state':'disabled'}
        try:
            decision=validate_decision(self.provider.decide(query))
        except (IntentUnavailable,ValueError,TypeError,KeyError,RuntimeError,OSError):
            return {**response,'state':'unavailable'}
        intent=decision['intent']['choice'];suggested_kind=decision['kind']['choice']
        return {**response,'state':'suggested','suggestion':{
            'intent':intent,'source':{'cover':'cover','text':'text','mixed':'all'}[intent],
            'kind':suggested_kind,'scores':decision,'scores_calibrated':False}}
    def close(self):
        if self.provider:self.provider.close()
