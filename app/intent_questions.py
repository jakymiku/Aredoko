"""Registered question contracts; experimental choices never load code/config remotely."""
import copy
import hashlib
import json

LEGACY_QUESTIONS={
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


ENGLISH_QUESTIONS={
    'intent':{'type':'choice','instructions':
        'Choose the main retrieval clue in this Japanese file-search query. Select mixed for vague recall, meaning or mood, or a combination of visible appearance and metadata.',
        'criteria':{
            'cover':'Visible appearance: colors, shapes, depicted objects or people, image composition or book cover. Not a title, filename or tag.',
            'text':'Explicit metadata: filename, title, creator, tag, extension or named item. The request mentions those clues.',
            'mixed':'Semantic content or mood; a general concept; vague recall; unknown clues; or both appearance and metadata.'}},
    'kind':{'type':'choice','instructions':
        'Which file type is EXPLICITLY requested? Do not infer file type from the subject matter. Choose any if the format is unknown or multiple types are requested.',
        'criteria':{
            'any':'No explicit file type, unknown type, vague request, or multiple different file types.',
            'book':'Book, doujinshi, manga, comic, CBZ, EPUB or PDF.',
            'image':'Picture, illustration, photo, wallpaper, PNG, JPEG or other single raster image.',
            'audio':'Music, song, voice, sound effect, BGM, WAV, MP3 or other audio file.',
            'video':'Video, movie, footage, MP4 or other video file.',
            'archive':'ZIP archive or compressed bundle; not a comic or explicitly named book.',
            'material':'Editable source/project file: PSD, CLIP, KRA, BLEND, SVG or other editable design asset. A template without a format can be any.'}}}

JAPANESE_QUESTIONS={
    'intent':{'type':'choice','instructions':'探す手がかりを選ぶ。名前・タグと見た目の両方ならmixed。内容の連想・雰囲気・曖昧な記憶もmixed。',
        'criteria':{'cover':'見た目：色、形、描かれた物や人、構図、表紙。名前やタグではない。',
                    'text':'文字情報：ファイル名、タイトル、作者、タグ、拡張子。これらを明示して探す。',
                    'mixed':'意味や内容、雰囲気、曖昧な記憶、手がかり不明、見た目と文字情報の両方。'}},
    'kind':{'type':'choice','instructions':'明示したファイルの種類だけを選ぶ。題材から種類を推測しない。種類不明や複数種類はany。',
        'criteria':{'any':'種類の指定なし、不明、または複数種類。テンプレートだけでは種類は不明。',
                    'book':'本、同人誌、漫画、CBZ、EPUB、PDF。',
                    'image':'画像、イラスト、写真、壁紙、PNG、JPEG。',
                    'audio':'音楽、曲、音声、効果音、BGM、WAV、MP3。',
                    'video':'動画、映像、ムービー、MP4。',
                    'archive':'ZIPや圧縮ファイル。本や漫画とは明示していない。',
                    'material':'編集用元データ、PSD、CLIP、KRA、BLEND、SVG。形式不明のテンプレートはany。'}}}

HYBRID_QUESTIONS={'intent':copy.deepcopy(LEGACY_QUESTIONS['intent']),
                  'kind':copy.deepcopy(JAPANESE_QUESTIONS['kind'])}
QUESTION_SETS={'v1':LEGACY_QUESTIONS,'v2-en':ENGLISH_QUESTIONS,'v2-ja':JAPANESE_QUESTIONS,'v2-hybrid':HYBRID_QUESTIONS}

def get_questions(name):
    if name not in QUESTION_SETS:raise ValueError('Unknown question set')
    return copy.deepcopy(QUESTION_SETS[name])

def question_key(name):
    # Ordered criteria are part of the decision contract; do not sort these keys.
    body=json.dumps(get_questions(name),ensure_ascii=False,separators=(',',':'))
    return name+':'+hashlib.sha256(body.encode('utf-8')).hexdigest()

def reversed_questions(questions):
    result=copy.deepcopy(questions)
    for row in result.values():row['criteria']=dict(reversed(list(row['criteria'].items())))
    return result
