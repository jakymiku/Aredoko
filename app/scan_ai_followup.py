"""AI follow-up scoped to the scanned roots and the exact owned worker.

No inference adapter or OS dependency lives here. The caller's AI service owns
its model/profile/worker; the scan only observes and may cancel that worker.
"""
from ai_scope import validate_scope


def run_scan_ai(ai, profiles, catalog, target_roots, cancelled, progress):
    scope=validate_scope(profiles.scope() if profiles is not None else {})
    registered={root['id'] for root in catalog.index.roots()}
    selected=scope['root_ids']
    allowed=set(target_roots) & registered
    if selected is not None:allowed.intersection_update(selected)
    if not allowed:
        return {'state':'skipped','error':'このフォルダは現在のAI索引の対象範囲外です。','processed':0,'total':0}
    # Preserve kind/shelf restrictions, narrowing roots without saving settings.
    scope={**scope,'root_ids':sorted(allowed)}
    if cancelled():return {'state':'cancelled','processed':0,'total':0}
    # Capture worker identity under the service's existing reentrant guard. A
    # later independently started index must never be observed/cancelled as ours.
    with ai.guard:
        started=ai.start(scope=scope)
        worker=ai.worker
    if worker is None:return started
    while True:
        with ai.guard:
            if ai.worker is not worker:
                return {'state':'failed','error':'別のAI操作へ切り替わったため、このスキャンの完了状態を確認できません。','processed':0,'total':0}
            alive=worker.is_alive()
            state=ai.status()
            if cancelled() and alive:
                ai.cancel_build()
                state={**state,'state':'cancelling'}
        progress(state)
        if not alive:return state
        worker.join(.1)
