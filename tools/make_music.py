"""Generate the invitation background music with ACE-Step 1.5 (acemusic.ai API).

Usage:  python tools/make_music.py [takes=3]
Writes: audio/pilihan-<n>.mp3 (normalised, faded, 96 kbps) — copy the chosen one to audio/muzik-latar.mp3
Key:    tools/.acemusic_key (git-ignored) or the ACE_MUSIC_API_KEY environment variable.
Same API call as Desktop/Masak bah/art/make_songs_ace.py.
"""
import base64, json, os, subprocess, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', 'audio')
API = 'https://api.acemusic.ai/v1/chat/completions'
MODEL = 'acemusic/acestep-v1.5-turbo'
SECONDS, BPM = 85, 78  # 85 s avoids the API's 504 gateway timeouts
CAPTION = ('Grand traditional Malay royal ceremonial instrumental for a prestigious school awards night. '
           'Gamelan Melayu, gambus, serunai, rebana and kompang, with lush orchestral strings and soft choir pads. '
           'Majestic, elegant palace procession, warm and celebratory, Malaysian heritage, cinematic. No vocals.')
LYRICS = '[instrumental]'


def key():
    k = os.environ.get('ACE_MUSIC_API_KEY')
    p = os.path.join(HERE, '.acemusic_key')
    if not k and os.path.exists(p):
        k = open(p).read().strip()
    if not k:
        sys.exit('No API key: put it in tools/.acemusic_key or ACE_MUSIC_API_KEY')
    return k


def generate(seed):
    body = {'model': MODEL, 'stream': False, 'thinking': True, 'seed': seed,
            'messages': [{'role': 'user', 'content': f'<prompt>{CAPTION}</prompt><lyrics>{LYRICS}</lyrics>'}],
            'audio_config': {'duration': SECONDS, 'bpm': BPM, 'format': 'mp3'}}
    req = urllib.request.Request(API, data=json.dumps(body).encode(), method='POST', headers={
        'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key(),
        'User-Agent': 'SriBitara-music/1.0'})  # the default Python agent is refused
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                msg = json.loads(r.read())['choices'][0]['message']
            return base64.b64decode(msg['audio'][0]['audio_url']['url'].split(',', 1)[1])
        except Exception as e:  # rate limits / timeouts: back off and retry
            print('   retry', attempt + 1, type(e).__name__, str(e)[:200])
            time.sleep(15 * (attempt + 1))
    raise RuntimeError('ACE Music API failed 4 times')


def finish(raw, dst):
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run([ff, '-y', '-loglevel', 'error', '-i', raw,
                    '-af', f'loudnorm=I=-18:TP=-2,afade=t=in:d=2,afade=t=out:st={SECONDS - 5}:d=5',
                    '-ac', '2', '-b:a', '96k', dst], check=True)


def main():
    takes = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    os.makedirs(OUT, exist_ok=True)
    for n in range(1, takes + 1):
        print(f'take {n}/{takes}: generating…')
        raw = os.path.join(OUT, f'_raw{n}.mp3')
        open(raw, 'wb').write(generate(seed=2026 + n))
        finish(raw, os.path.join(OUT, f'pilihan-{n}.mp3'))
        os.remove(raw)
        print('   ->', f'audio/pilihan-{n}.mp3', os.path.getsize(os.path.join(OUT, f'pilihan-{n}.mp3')) // 1024, 'KB')


if __name__ == '__main__':
    main()
