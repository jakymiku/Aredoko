"""Small generated-only native audit for contextual detail commands."""
import subprocess
import wave
import zipfile

from create_preview_fixture import png
from video_previews import _executable


def create_media(media):
    for i in range(2):
        (media / f'image-{i}.png').write_bytes(png(color=(64 + i * 30, 110, 160)))
    for name in ('book.cbz', 'archive.zip'):
        with zipfile.ZipFile(media / name, 'w') as archive:
            archive.writestr('page01.png', png(color=(120, 100, 170)))
    with wave.open(str(media / 'sound.wav'), 'wb') as audio:
        audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(8000)
        audio.writeframes(b'\0\0' * 8000)
    subprocess.run([_executable('ffmpeg'), '-nostdin', '-hide_banner', '-loglevel', 'error',
                    '-f', 'lavfi', '-i', 'color=c=blue:s=160x120:r=10:d=1',
                    '-an', '-c:v', 'mpeg4', '-threads', '1', '-movflags', '+faststart',
                    str(media / 'video.mp4')], check=True, timeout=15,
                   creationflags=subprocess.CREATE_NO_WINDOW)


def audit(ui, tree, shot, check, catalog, *, navigation_only=False):
    buttons = ('BtnOpenImage', 'BtnOpenBook', 'BtnOpenVideo', 'BtnOpenAudio')
    items = catalog.search()['items']
    def select(item_id):
        selector = 'Item' + str(item_id)
        tree()  # Refresh cached UIA peers after the details pane changes layout.
        try:
            ui('invoke', selector, '--action', 'select')
        except RuntimeError as error:
            if 'Element is no longer accessible' not in str(error):
                raise
            tree()
            ui('invoke', selector, '--action', 'select')  # One idempotent stale-peer retry.
    cases = () if navigation_only else (('image', buttons[0]), ('book', buttons[1]),
                                      ('archive', buttons[1]), ('video', buttons[2]), ('audio', buttons[3]))
    for kind, button in cases:
        item = next(row for row in items if row['kind'] == kind)
        select(item['id'])
        ui('wait-for', button, '-p', 'IsEnabled', '--value', 'True', '-t', '10000')
        visible = tree()
        actual = {key for key in buttons if key in visible and not visible[key].get('isOffscreen', True)}
        check(kind + ': exactly its own detail open command', actual == {button})
        tag_visible = 'BtnTagSuggestions' in visible and not visible['BtnTagSuggestions'].get('isOffscreen', True)
        check(kind + ': visual tag review is contextual', tag_visible == (kind in ('image', 'book', 'archive')))
        if kind in ('image', 'book', 'audio'):
            shot(kind + '-detail')
    image = next(row for row in items if row['kind'] == 'image')
    select(image['id'])
    ui('wait-for', 'BtnOpenImage', '-p', 'IsEnabled', '--value', 'True', '-t', '10000')
    ui('set-value', 'TxtTags', 'detail-ui-generated')
    ui('invoke', 'BtnCloseDetails')
    ui('invoke', 'BtnDetails')
    ui('wait-for', 'TxtTags', '--value', 'detail-ui-generated', '-t', '5000')
    check('hidden detail preserves unsaved tag', True)
    ui('invoke', 'BtnSave')
    ui('wait-for', 'BtnSave', '-p', 'IsEnabled', '--value', 'False', '-t', '10000')
    ui('wait-for', 'TxtTags', '-p', 'IsEnabled', '--value', 'True', '-t', '10000')
    check('explicit save reaches generated catalog', catalog.search(query='detail-ui-generated')['total'] == 1)
    ui('invoke', 'NavShelf')
    shelf = catalog.shelf_descriptors()[0]
    ui('wait-for', 'ShelfOpen' + str(shelf['id']), '-t', '10000')
    shot('shelf-hub')
    ui('invoke', 'ShelfOpen' + str(shelf['id']))
    ui('wait-for', 'Item' + str(image['id']), '-t', '10000')
    select(image['id'])
    ui('wait-for', 'TxtTags', '--value', 'detail-ui-generated', '-t', '10000')
    check('shelf navigation reuses library and saved metadata', True)
