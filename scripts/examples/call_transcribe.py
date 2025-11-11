#!/usr/bin/env python3
import argparse
import io
import json
import os
import shutil
import sys
import tempfile
import urllib.parse
import urllib.request
import subprocess
import re


def detect_ffplay():
    return shutil.which("ffplay")


def detect_afplay():
    return shutil.which("afplay")


def post_audio(base: str, path: str, return_mode: str, voice: str, llm_model: str = None, system: str = None):
    with open(path, 'rb') as f:
        data = f.read()
    ctype = guess_ctype(path)
    params = {"return": return_mode}
    if return_mode in ("tts", "llm_tts"):
        params["voice"] = voice
    if return_mode == "llm_tts":
        if llm_model:
            params["llm_model"] = llm_model
        if system:
            params["system"] = system
    url = build_url(base, "/transcribe", params)
    req = urllib.request.Request(url, data=data, headers={"Content-Type": ctype, "User-Agent": "waifu-client/1.0"}, method='POST')
    return urllib.request.urlopen(req)


def guess_ctype(path: str) -> str:
    low = path.lower()
    if low.endswith('.wav'):
        return 'audio/wav'
    if low.endswith('.mp3'):
        return 'audio/mpeg'
    if low.endswith('.ogg'):
        return 'audio/ogg'
    return 'application/octet-stream'


def build_url(base: str, p: str, params: dict):
    if base.endswith('/'):
        base = base[:-1]
    q = urllib.parse.urlencode(params)
    return f"{base}{p}?{q}" if q else f"{base}{p}"


def parse_multipart(resp, on_json, on_audio):
    ctype = resp.getheader('Content-Type') or ''
    m = re.search(r"boundary=\s*\"?([^\";]+)\"?", ctype, flags=re.IGNORECASE)
    boundary = m.group(1) if m else (resp.getheader('X-Boundary') or '').strip()
    if not boundary:
        raise RuntimeError('Missing multipart boundary')
    bline = ("--" + boundary).encode('utf-8')
    end_marker = ("--" + boundary + "--").encode('utf-8')

    def readline():
        return resp.readline()

    # sync to first boundary
    while True:
        line = readline()
        if not line:
            return
        if line.strip() == bline:
            break

    while True:
        headers = {}
        while True:
            line = readline()
            if not line:
                return
            if line in (b"\r\n", b"\n"):
                break
            key, _, val = line.decode('utf-8', errors='ignore').partition(':')
            headers[key.lower().strip()] = val.strip()
        length = int(headers.get('content-length', '0'))
        ctype = headers.get('content-type', '')
        body = resp.read(length) if length else b''
        if 'application/json' in ctype:
            on_json(body)
        elif 'audio/' in ctype or ctype == 'application/octet-stream':
            on_audio(body, ctype)

        # read trailing CRLF
        _ = resp.read(2)
        line = readline()
        if not line or line.strip() == end_marker:
            return
        if line.strip() != bline:
            return


def save_and_play(audio_bytes: bytes, ctype: str, play: bool):
    suffix = '.mp3' if 'mpeg' in ctype else '.wav'
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
        out = f.name
        f.write(audio_bytes)
    print(f"Saved audio to {out}")
    if not play:
        return
    ff = detect_ffplay()
    af = detect_afplay()
    player = ff or af
    if not player:
        print("No player found. Install ffmpeg or use afplay on macOS.", file=sys.stderr)
        return
    args = [player]
    if ff:
        args += ["-nodisp", "-autoexit", "-loglevel", "quiet", out]
    else:
        args += [out]
    subprocess.run(args, check=False)


def main():
    ap = argparse.ArgumentParser(description='POST audio to /transcribe and parse the multipart response')
    ap.add_argument('--base', default='http://127.0.0.1:8787', help='Base server URL')
    ap.add_argument('--file', required=True, help='Path to audio file (.mp3 or .wav)')
    ap.add_argument('--return', dest='ret', choices=['original', 'tts', 'none', 'llm_tts'], default='original', help='What audio to return')
    ap.add_argument('--voice', default='Brian', help='TTS voice if return=tts/llm_tts')
    ap.add_argument('--session', default='cli', help='Conversation session id for llm_tts')
    # Leave blank to use server default (HF Mistral v0.2)
    ap.add_argument('--llm-model', default='', help='LLM model for llm_tts (e.g., mistralai/Mistral-7B-Instruct-v0.2)')
    ap.add_argument('--system', default='', help='Optional system prompt for the model')
    ap.add_argument('--play', action='store_true', help='Play the returned audio')
    args = ap.parse_args()

    with post_audio(args.base + (f"?session={urllib.parse.quote(args.session)}" if args.ret == 'llm_tts' else ''), args.file, args.ret, args.voice, args.llm_model, args.system) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} {resp.reason}")
        ctype = resp.getheader('Content-Type') or ''
        if 'multipart/mixed' in ctype:
            transcript = None
            audio_bytes = None
            audio_ctype = 'application/octet-stream'

            def on_json(b: bytes):
                nonlocal transcript
                try:
                    transcript = json.loads(b.decode('utf-8', errors='ignore'))
                except Exception:
                    print('Failed to parse JSON transcript', file=sys.stderr)

            def on_audio(b: bytes, ct: str):
                nonlocal audio_bytes, audio_ctype
                audio_bytes = b
                audio_ctype = ct

            parse_multipart(resp, on_json, on_audio)
            print('Transcript:')
            print(json.dumps(transcript, indent=2))
            if audio_bytes:
                save_and_play(audio_bytes, audio_ctype, args.play)
        else:
            # JSON response only
            body = resp.read()
            print(body.decode('utf-8', errors='ignore'))


if __name__ == '__main__':
    main()

