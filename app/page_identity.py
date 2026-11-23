"""Opaque page identities; source revisions still determine evidence freshness."""
import hashlib
import json


def describe_page(item_id, kind, locator, occurrence, page, mime, size):
    # Never expose or accept a locator/path through the public API. A filename
    # keeps its ID when another page is inserted; renames are not inferred.
    identity = ['aredoko-page-v1', item_id, kind, locator, occurrence]
    page_id = hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode('utf-8')).hexdigest()
    return {'page_id': page_id, 'page': page, 'mime': mime, 'size_bytes': size}
