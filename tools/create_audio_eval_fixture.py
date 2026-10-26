"""Small offline R06 fixture: four synthesized utterances and four signals.

Existing Windows Haruka Desktop writes WAV files only; no speakers/microphone,
downloads, inference or user media. Numeric filenames never reveal the answer.
"""
import argparse,hashlib,json,math,os,random,struct,wave
from pathlib import Path
REPO=Path(__file__).resolve().parents[1]
RATE=16000


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();target=args.output.resolve()
    if os.name!='nt' or target.exists() or not target.is_relative_to(REPO/'data/ai-ui'):parser.error('New dedicated Windows fixture required')
    target.mkdir(parents=True);media=target/'media';media.mkdir()
    utterances=[('001.wav','赤い傘を教室に忘れました。','赤い傘を教室に忘れた話','A red umbrella was left in a classroom'),
                ('002.wav','会議は水曜日の午後三時に始まります。','水曜日の午後三時からの会議','A meeting at three on Wednesday afternoon'),
                ('003.wav','図書館で青い本を探しています。','図書館で青い本を探す話','Looking for a blue book in the library'),
                ('004.wav','温かいコーヒーとチョコレートをください。','温かいコーヒーとチョコレートの注文','Ordering warm coffee and chocolate')]
    # Existing Python COM API: no PowerShell execution-policy changes, script
    # execution, dependency installation or registry edits are required.
    import pythoncom
    from win32com.client import Dispatch
    pythoncom.CoInitialize();speaker=stream=None
    try:
        speaker=Dispatch('SAPI.SpVoice')
        selected=[v for v in speaker.GetVoices() if v.Id.casefold()=='hkey_local_machine\\software\\microsoft\\speech\\voices\\tokens\\tts_ms_ja-jp_haruka_11.0']
        if len(selected)!=1:raise RuntimeError('Existing offline Haruka Desktop voice required; no download attempted')
        speaker.Voice=selected[0]
        for name,text,_,_ in utterances:
            path=media/name
            if path.exists():raise FileExistsError(path)
            stream=Dispatch('SAPI.SpFileStream');stream.Open(str(path),3,False)
            speaker.AudioOutputStream=stream  # Never use a speaker/device.
            try:speaker.Speak(text)
            finally:stream.Close();stream=None
        voice={'voice':speaker.Voice.GetDescription(),'files':len(utterances),'output':'files-only','external_download':False,'api':'SAPI COM via existing pywin32'}
    finally:
        if stream is not None:stream.Close()
        speaker=None;stream=None;pythoncom.CoUninitialize()
    rng=random.Random(7301);notes=[261.63,329.63,392.0,523.25,392.0,329.63,293.66,261.63]
    melody=[];rhythm=[];noise=[]
    for i in range(4*RATE):
        t=i/RATE;local=t%.5;frequency=notes[min(7,int(t/.5))]
        melody.append(.4*math.sin(2*math.pi*frequency*t)*math.exp(-local*6))
        beat=t%.25;rhythm.append(.6*(rng.random()*2-1)*math.exp(-beat*50))
        noise.append(.22*(rng.random()*2-1))
    for name,samples in [('005.wav',noise),('006.wav',melody),('007.wav',rhythm),('008.wav',[x*.45 for x in melody])]:
        with wave.open(str(media/name),'wb') as stream:
            stream.setnchannels(1);stream.setsampwidth(2);stream.setframerate(RATE)
            stream.writeframes(b''.join(struct.pack('<h',round(max(-1,min(1,x))*30000)) for x in samples))
    items=[]
    for path in sorted(media.glob('*.wav')):
        with wave.open(str(path),'rb') as source:
            duration=source.getnframes()/source.getframerate()
            if not 0<duration<30:raise ValueError('Bounded generated clip required')
            items.append({'id':path.stem,'file':path.name,'seconds':duration,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                          'domain':'speech' if path.stem in {'001','002','003','004'} else 'synthetic-signal'})
    queries=[]
    for name,_,ja,en in utterances:
        for language,text in [('ja',ja),('en',en)]:queries.append({'axis':'speech_'+language,'text':text,'expected':[Path(name).stem]})
    for text,expected in [('雑音やノイズが聞こえる','005'),('ゆっくりしたメロディーが流れる音楽','006'),('速いリズムで打楽器が鳴る音','007')]:
        queries.append({'axis':'synthetic_sound','text':text,'expected':[expected,'008'] if expected=='006' else [expected]})
    manifest={'format':'aredoko-generated-audio-eval-v1','voice':voice,'items':items,'queries':queries,
              'similarity':[{'origin':'006','expected':['008']},{'origin':'008','expected':['006']}],
              'limits':'Synthetic speech and signals only; no real environmental recordings, instruments, songs, ASR comparison or general quality guarantee.'}
    (target/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'pass':True,'items':len(items),'queries':len(queries),'voice':voice},ensure_ascii=False));return 0


if __name__=='__main__':raise SystemExit(main())
