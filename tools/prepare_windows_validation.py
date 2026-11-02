"""Prepare generated media and a manual checklist beside a sealed basic ZIP.

Does not launch apps, change settings, or claim clean-Windows acceptance.
"""
import argparse,json,os,zipfile
from pathlib import Path
from create_preview_fixture import png
from release_runtime import digest,verify_release
from storage_lease import plain_path,storage_parent

REPO=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();release=plain_path(args.release,directory=True);out=Path(os.path.abspath(args.output));archive=out.with_suffix('.zip')
    if not out.is_relative_to(REPO/'dist') or out.is_relative_to(release) or out.exists() or archive.exists():parser.error('New independent dist output required')
    manifest=verify_release(release)
    if manifest.get('ai_runtime_bundled') is not False or manifest.get('models_bundled') is not False:parser.error('Basic ZIP only')
    app_zip=plain_path(release.parent/'Aredoko-windows-x64.zip')
    # Pair the selected sealed directory with its archive before publishing a
    # checklist. Payload hashing remains the release builder's responsibility.
    with zipfile.ZipFile(app_zip) as application:
        expected={'Aredoko/'+row['path'] for row in manifest['entries']}|{'Aredoko/manifest.json','Aredoko/sha256sums.txt'}
        names=application.namelist()
        if len(names)!=len(expected) or set(names)!=expected:raise ValueError('Application ZIP inventory does not match the selected release')
        for name in ('manifest.json','sha256sums.txt'):
            if application.read('Aredoko/'+name)!=(release/name).read_bytes():raise ValueError('Application ZIP metadata does not match the selected release: '+name)
        if any(application.getinfo('Aredoko/'+row['path']).file_size!=row['bytes'] for row in manifest['entries']):raise ValueError('Application ZIP sizes do not match the selected release')
    release_identity={'version':manifest.get('version'),'created_at':manifest.get('created_at'),'platform':manifest.get('platform'),'source_revision':manifest.get('source_revision')}
    identity={'application_zip':app_zip.name,'zip_bytes':app_zip.stat().st_size,'zip_sha256':digest(app_zip),'manifest_sha256':digest(release/'manifest.json'),'release_identity':release_identity,'archive_metadata_matches_release':True,'clean_windows_verified':False}
    storage_parent(out);out.mkdir();media=out/'media';media.mkdir()
    first=png(color=(88,111,190));second=png(color=(73,133,111))
    (media/'blue-image.png').write_bytes(first);(media/'green-image.png').write_bytes(second)
    with zipfile.ZipFile(media/'two-pages.cbz','x',compression=zipfile.ZIP_DEFLATED) as book:
        book.writestr('001.png',first);book.writestr('002.png',second)
    identity['media_sha256']={p.name:digest(p) for p in sorted(media.iterdir())}
    (out/'candidate.json').write_text(json.dumps(identity,indent=2),encoding='utf-8')
    result={'application_zip_sha256':identity['zip_sha256'],'manifest_sha256':identity['manifest_sha256'],'release_identity':release_identity,'windows_version':None,'development_python_dotnet_sdk_absent':None,'additional_runtime_installed_before_test':None,
            'normal_exe_start':None,'three_generated_items_found':None,'image_and_cbz_viewing':None,'tag_shelf_favorite_saved':None,
            'saved_data_after_restart':None,'saved_data_after_relocation':None,'original_media_hashes_unchanged':None,
            'failure_stage':None,'displayed_error':None,'log_location':None,'clean_windows_verified':False}
    (out/'result-template.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    (out/'はじめに.txt').write_text(
        'Aredoko 別Windowsの基本版確認セット\n\n'
        'このセットは検証用の生成画像2枚と2ページCBZだけです。アプリやAI環境は含みません。合格済みという意味ではありません。\n'
        '普段のライブラリがない検証用Windowsユーザーで、同じ候補の基本ZIPと一緒に使ってください。\n\n'
        '1. candidate.jsonのZIP SHA256と候補を照合し、アプリを新しい場所へすべて解凍します。release_identityは検証済みmanifestの版・作成日時・対象OS・記録されたソースrevisionです。source_revisionがnullなら元のmanifestに記録がなく、未確認です。開発用Python/.NET SDKや追加runtimeを先に導入せず、OS版と既存環境を記録します。\n'
        '2. 通常のAredoko.exeを開き、初回案内とライブラリが出ることを確認します。Check-Startup.cmdの空DBで代用しません。\n'
        '3. このセットのmediaフォルダを登録し、「アイテム一覧だけ取得」を実行。PNG2件とCBZ1件が見つかることを確認します。AIは準備しません。\n'
        '4. ファイル名検索、画像表示、CBZの2ページ送り、タグ・棚・お気に入りの保存を確認します。\n'
        '5. アプリを閉じて再起動し、登録内容と編集結果が残ることを確認します。\n'
        '6. 終了後、同じアプリ一式を空白・日本語を含む別フォルダに配置し、同じユーザーでAredoko.exeを開いて保存内容を確認します。旧フォルダへ上書きしません。\n'
        '7. candidate.jsonのmedia_sha256と原本を照合し、result-template.jsonのコピーに結果を記録します。失敗時は段階・表示文・ログの場所を残します。\n\n'
        'このセットは設定変更・自動送信・モデル取得・ファイル削除を行いません。実行ファイルやスクリプトは含みません。\n',encoding='utf-8-sig')
    files=sorted(p for p in out.rglob('*') if p.is_file())
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for p in files:z.write(p,p.relative_to(out).as_posix())
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None or any(z.read(p.relative_to(out).as_posix())!=p.read_bytes() for p in files):raise RuntimeError('Validation kit ZIP mismatch')
    print(json.dumps({'output':str(archive),'files':len(files),'sha256':digest(archive),'application_zip_sha256':identity['zip_sha256'],'clean_windows_verified':False}))


if __name__=='__main__':main()
