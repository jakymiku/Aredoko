"""Bounded file-name labels for transient local preparation progress."""
import re

MAX_TITLE=160


def item_title(value):
    if not isinstance(value,str):return ''
    # Catalog titles are basenames. Never expose an accidentally supplied path.
    name=re.split(r'[/\\]',value)[-1]
    name=''.join(char if char.isprintable() else ' ' for char in name).strip()
    if len(name.encode('utf-16-le'))//2<=MAX_TITLE:return name
    chars=[];units=0
    for char in name:
        cost=2 if ord(char)>0xffff else 1
        if units+cost>MAX_TITLE-1:break
        chars.append(char);units+=cost
    return ''.join(chars)+'…'
