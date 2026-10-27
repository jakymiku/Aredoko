"""Read-only feature/dependency plan for optional first-run AI setup.

Uses existing configuration/catalog snapshots only. Never starts a download,
model, GPU probe, index, file discovery or settings mutation. Files present
does not mean inference/hardware compatibility has been tested.
"""
from copy import deepcopy

from ai_profiles import ModelProfile
from model_locations import ModelTarget

FEATURES=(
    ('semantic','意味検索','text','ファイル名・タグ等の意味で探します。画像検索は画像対応モデルが必要です。'),
    ('image_similarity','類似画像検索','cover','画像・表紙から似た作品を探します。先に画像の索引を作成します。'),
    ('video','動画の内容検索','video','全区間の動画索引を作成します。動画内の音声は対象外です。'),
    ('audio','音声・音楽の内容検索','audio','音声の内容・特徴を探します。文字起こしは保存しません。'),
)
CATALOG_FIELDS=('catalog_id','name','kind','revision','bytes','license','license_url','source_hosts',
                'unpacked_bytes','unpacked_files','model_target')


def plan_setup(body,*,profile,environment,catalogs):
    if type(body) is not dict or set(body)!={'features'}:raise ValueError('Select setup features only')
    selected=body['features'];known={row[0] for row in FEATURES}
    if (type(selected) is not list or len(selected)>len(FEATURES)
            or any(type(key) is not str or key not in known for key in selected)
            or len(set(selected))!=len(selected)):raise ValueError('Invalid or duplicate setup feature')
    result={'version':1,'basic_available':True,'ai_optional':True,'skip_ai':not selected,
            'features':[],'requirements':[],'selected_catalog_ids':[],'known_download_bytes':0,
            'total_download_bytes':0,'unresolved_requirements':[],
            'unresolved_features':[],'can_download_all_missing':True,
            'inference_checked_by_plan':False,'hardware_checked_by_plan':False,
            'settings_saved':False,'acquisition_started':False,'restart_required':False}
    # Skipping AI must not even inspect a runtime/model directory or catalog.
    if not selected:return result
    if not callable(environment) or not callable(catalogs):raise ValueError('Application snapshots required')
    for key,label,modality,description in FEATURES:
        if key not in selected:continue
        supported=isinstance(profile,ModelProfile) and (modality in profile.modalities if modality in ('text','cover') else profile.adapter=='embeddinggemma2')
        result['features'].append({'id':key,'label':label,'supported':supported,'description':description,
            'requires_indexing':True,'requirements':['embedding-runtime','embedding-model'] if supported else [],
            'unavailable_reason':None if supported else 'choose_compatible_model_profile'})
        if not supported:result['unresolved_features'].append(key)
    result['can_download_all_missing']=not result['unresolved_features']
    if not any(feature['supported'] for feature in result['features']):return result
    state=environment();available=catalogs()
    if type(state) is not dict or type(available) is not dict or type(available.get('catalogs')) is not list:
        raise ValueError('Invalid setup snapshot')
    target=ModelTarget.for_profile('embedding',profile).to_dict()
    result['restart_required']=state.get('restart_required') is True
    rows=available['catalogs']
    for key,kind,present,target_identity in (
        ('embedding-runtime','runtime',state.get('runtime',{}),None),
        ('embedding-model','model',state.get('model',{}),target),
    ):
        if type(present) is not dict:raise ValueError('Invalid dependency state')
        candidates=[{field:deepcopy(row[field]) for field in CATALOG_FIELDS if field in row}
                    for row in rows if row.get('kind')==kind and
                    (kind=='runtime' or row.get('model_target')==target_identity)]
        candidates.sort(key=lambda row:row['catalog_id'])
        files_present=present.get('ready') is True
        # Do not choose arbitrarily between multiple registered distributions.
        selected_catalog=candidates[0] if not files_present and len(candidates)==1 else None
        dependency={'id':key,'kind':kind,'files_present':files_present,
                    'state':present.get('state','unknown'),'model_target':target_identity,
                    'download_candidates':candidates,'selected_catalog_id':selected_catalog['catalog_id'] if selected_catalog else None,
                    'action':('none' if files_present else 'review_download' if selected_catalog else
                              'choose_download' if candidates else 'select_existing_environment' if kind=='runtime' else 'select_existing_model'),
                    'automatic_download_published':bool(candidates),
                    'compatibility_check_required':True}
        result['requirements'].append(dependency)
        if selected_catalog:
            result['selected_catalog_ids'].append(selected_catalog['catalog_id'])
            result['known_download_bytes']+=selected_catalog['bytes']
        elif not files_present:result['unresolved_requirements'].append(key)
    result['total_download_bytes']=None if result['unresolved_requirements'] else result['known_download_bytes']
    result['can_download_all_missing']=not result['unresolved_requirements'] and not result['unresolved_features']
    return result
