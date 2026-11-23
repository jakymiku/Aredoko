"""Finite, path-free startup failures shared by private inference workers.

No dependency is imported or loaded here. A missing DLL is not proof that
installing a particular redistributable will fix it; callers offer inspection.
"""

STARTUP_ERRORS={
    'DependencyUnavailable':('ai_runtime_dependencies_unavailable','AI runtime dependencies unavailable'),
    'ArchitectureMismatch':('ai_runtime_architecture_incompatible','AI runtime architecture incompatible'),
    'InitializationFailed':('ai_runtime_initialization_failed','AI runtime initialization failed'),
}


def startup_error(error):
    if isinstance(error,OSError) and getattr(error,'winerror',None)==193:
        code='ArchitectureMismatch'
    elif isinstance(error,ImportError) or isinstance(error,OSError) and getattr(error,'winerror',None) in (126,127,1114):
        code='DependencyUnavailable'
    else:code='InitializationFailed'
    return {'error':code}
