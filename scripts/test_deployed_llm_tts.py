#!/usr/bin/env python3
import argparse
import json
import sys
import urllib.request


def post_json(base: str, text: str, voice: str, session: str, model: str, debug: bool = False) -> bytes:
    if base.endswith('/'):
        base = base[:-1]
    url = f"{base}/llm_tts" + ("?debug=1" if debug else "")
    payload = json.dumps({
        "text": text,
        "voice": voice,
        "session": session,
        "llm_model": model,
    }).encode('utf-8')
    req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json', 'User-Agent': 'deployed-llm-tts-test/1.0'}, method='POST')
    try:
        with urllib.request.urlopen(req) as resp:
            if resp.status != 200:
                body = resp.read().decode('utf-8', errors='ignore')
                raise RuntimeError(f"HTTP {resp.status}: {body}")
            return resp.read(), (resp.getheader('Content-Type') or 'audio/mpeg')
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='ignore')
        raise RuntimeError(f"HTTP {e.code} {e.reason}: {body}")


def save_and_play(buf: bytes, ctype: str):
    import tempfile, shutil, subprocess
    suffix = '.mp3' if 'mpeg' in (ctype or '') else '.wav'
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
        path = f.name
        f.write(buf)
    print('Saved to', path)
    player = shutil.which('afplay') or shutil.which('ffplay')
    if player:
        args = [player]
        if player.endswith('ffplay'):
            args += ['-nodisp', '-autoexit', '-loglevel', 'quiet', path]
        else:
            args += [path]
        subprocess.run(args, check=False)
    else:
        print('No mac player found; install ffmpeg for ffplay or play file manually.')


def main():
    ap = argparse.ArgumentParser(description='Test a deployed /llm_tts endpoint with JSON text → audio reply')
    ap.add_argument('--base', default='https://tts-waifu.onrender.com', help='Deployed base URL (default: Render tts-waifu example)')
    ap.add_argument('--text', default='Say hello in five words.', help='Test text')
    ap.add_argument('--voice', default='Brian', help='Voice')
    ap.add_argument('--session', default='test', help='Session id')
    ap.add_argument('--model', default='gemini-2.0-flash', help='Gemini model id')
    ap.add_argument('--debug', action='store_true', help='Add ?debug=1 to request')
    args = ap.parse_args()

    # Basic base URL validation
    if '://' not in args.base or args.base.endswith('://') or args.base.endswith(':///'):
        print('Invalid --base URL. Example: https://your-service.onrender.com', file=sys.stderr)
        sys.exit(2)

    try:
        audio, ctype = post_json(args.base, args.text, args.voice, args.session, args.model, args.debug)
        save_and_play(audio, ctype)
    except Exception as e:
        print('Error:', e, file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
