#!/usr/bin/env python3
"""
Prod mic client for lightweight devices.
- Records locally, sends WAV to remote AI endpoint /transcribe?return=llm_tts
- All ASR + LLM + TTS runs on the server.
"""
import argparse
import io
import json
import os
import queue
import shutil
import sys
import time
import wave
import urllib.parse
import urllib.request

try:
    import numpy as np
    import sounddevice as sd
except Exception:
    print("Please install dependencies: pip3 install sounddevice numpy", file=sys.stderr)
    raise


def record_once(samplerate=16000, channels=1, start_threshold=0.02, stop_threshold=0.01, min_speech_ms=150, trailing_silence_ms=600, max_seconds=12.0):
    q = queue.Queue()
    started = False
    speech_start_ts = None
    last_voice_ts = None
    collected = []
    blocksize = 1024
    silence_limit_samples = int(trailing_silence_ms * samplerate / 1000)
    min_speech_samples = int(min_speech_ms * samplerate / 1000)
    max_samples = int(max_seconds * samplerate)
    scale = 32768.0

    def cb(indata, frames, time_info, status):
        if status:
            pass
        q.put(indata.copy())

    with sd.InputStream(samplerate=samplerate, channels=channels, dtype='int16', blocksize=blocksize, callback=cb):
        total_samples = 0
        while True:
            try:
                data = q.get(timeout=0.5)
            except queue.Empty:
                if started and (time.time() - last_voice_ts) * samplerate > silence_limit_samples:
                    break
                continue
            x = np.frombuffer(data.tobytes(), dtype=np.int16)
            total_samples += len(x)
            level = float(np.sqrt(np.mean((x.astype(np.float32) / scale) ** 2)) + 1e-9)
            if not started:
                if level >= start_threshold:
                    started = True
                    speech_start_ts = time.time()
                    last_voice_ts = time.time()
                    collected.append(x)
                else:
                    continue
            else:
                collected.append(x)
                if level >= stop_threshold:
                    last_voice_ts = time.time()
                speech_dur_samples = int((time.time() - speech_start_ts) * samplerate)
                since_voice_samples = int((time.time() - last_voice_ts) * samplerate)
                if speech_dur_samples >= min_speech_samples and since_voice_samples >= silence_limit_samples:
                    break
            if total_samples >= max_samples:
                break

    if not collected:
        return b""
    y = np.concatenate(collected).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(samplerate)
        wf.writeframes(y.tobytes())
    return buf.getvalue()


def build_url(base: str, p: str, params: dict):
    if base.endswith('/'):
        base = base[:-1]
    q = urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, '')})
    return f"{base}{p}?{q}" if q else f"{base}{p}"


def post_llm_tts(base: str, wav_bytes: bytes, session: str, voice: str, llm_model: str, system: str):
    url = build_url(base, "/transcribe", {
        "return": "llm_tts",
        "voice": voice,
        "session": session,
        "llm_model": llm_model,
        "system": system,
    })
    req = urllib.request.Request(url, data=wav_bytes, headers={"Content-Type": "audio/wav", "User-Agent": "prod-mic/1.0"}, method='POST')
    return urllib.request.urlopen(req)

# Helpers to parse server response and play audio
def parse_multipart(resp, on_json, on_audio):
    import re
    ctype = resp.getheader('Content-Type') or ''
    m = re.search(r"boundary=\s*\"?([^\";]+)\"?", ctype, flags=re.IGNORECASE)
    boundary = m.group(1) if m else (resp.getheader('X-Boundary') or '').strip()
    if not boundary:
        raise RuntimeError('Missing multipart boundary')
    raw = resp.read()
    sep = ("--" + boundary).encode('utf-8')
    parts = raw.split(sep)
    for part in parts:
        part = part.strip()
        if not part or part == b'--':
            continue
        if part.startswith(b"\r\n"):
            part = part[2:]
        if part.endswith(b"--"):
            part = part[:-2]
        if b"\r\n\r\n" not in part:
            continue
        header_blob, body = part.split(b"\r\n\r\n", 1)
        headers = {}
        for line in header_blob.split(b"\r\n"):
            if not line:
                continue
            key, _, val = line.decode('utf-8', errors='ignore').partition(':')
            headers[key.lower().strip()] = val.strip()
        pctype = headers.get('content-type', '')
        if 'application/json' in pctype:
            on_json(body)
        elif 'audio/' in pctype or pctype == 'application/octet-stream':
            on_audio(body, pctype)

def save_and_play(audio_bytes: bytes, ctype: str):
    import tempfile, shutil, subprocess
    suffix = '.mp3' if 'mpeg' in ctype else '.wav'
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
        out = f.name
        f.write(audio_bytes)
    print(f"Saved audio to {out}")
    # Prefer mpg123, then ffmpeg->aplay, then ffplay/afplay
    mpg = shutil.which('mpg123')
    if mpg:
        subprocess.run([mpg, '-q', out], check=False)
        return
    aplay = shutil.which('aplay')
    ffmpeg = shutil.which('ffmpeg')
    if aplay and ffmpeg:
        p1 = subprocess.Popen([ffmpeg, '-loglevel', 'error', '-i', out, '-f', 'wav', '-'], stdout=subprocess.PIPE)
        assert p1.stdout is not None
        subprocess.run([aplay, '-q'], stdin=p1.stdout, check=False)
        p1.stdout.close()
        p1.wait()
        return
    player = shutil.which('ffplay') or shutil.which('afplay')
    if player:
        args = [player]
        if player.endswith('ffplay'):
            args += ['-nodisp', '-autoexit', '-loglevel', 'quiet', out]
        else:
            args += [out]
        subprocess.run(args, check=False)
    else:
        print('No audio player found. Install mpg123 or ffmpeg+aplay for best results.', file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description='Prod mic client — all compute on server via /transcribe?return=llm_tts')
    # Hardcoded, sensible local defaults; flags remain optional overrides
    ap.add_argument('--base', default='http://127.0.0.1:8787', help='AI server base URL (default: http://127.0.0.1:8787)')
    ap.add_argument('--session', default='prod', help='Conversation session id (default: prod)')
    ap.add_argument('--voice', default='Joanna', help='TTS voice (default: Joanna)')
    ap.add_argument('--llm-model', default='gemini-2.0-flash', help='Gemini model id (default: gemini-2.0-flash)')
    ap.add_argument('--system', default='', help='Optional system prompt')
    ap.add_argument('--max-seconds', type=float, default=12.0, help='Max capture length per turn')
    ap.add_argument('--no-play', action='store_true', help='Do not play returned audio')
    args = ap.parse_args()

    print(f"Prod mic ready. Base={args.base} Session={args.session} Voice={args.voice} Model={args.llm_model}")
    print("Press Enter to speak; /quit to exit; /reset to clear history")

    while True:
        try:
            cmd = input('\nPress Enter to speak (or command): ').strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if cmd == '/quit':
            break
        if cmd == '/reset':
            try:
                url = build_url(args.base, '/llm', {"session": args.session, "reset": '1'})
                data = json.dumps({"text": ""}).encode('utf-8')
                req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json', 'User-Agent': 'prod-mic/1.0'})
                urllib.request.urlopen(req).read()
                print('(history cleared)')
            except Exception as e:
                print('Reset failed:', e)
            continue

        print('Speak now…')
        wav = record_once(max_seconds=args.max_seconds)
        if not wav:
            print('No speech detected; try again.')
            continue
        try:
            with post_llm_tts(args.base, wav, args.session, args.voice, args.llm_model, args.system) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"HTTP {resp.status} {resp.reason}")
                ctype = resp.getheader('Content-Type') or ''
                if 'multipart/mixed' not in ctype:
                    body = resp.read()
                    print(body.decode('utf-8', errors='ignore'))
                    continue

                # Robust multipart parser (buffered)
                result = {"transcript": None, "llm": None}
                audio = {"buf": None, "ctype": 'application/octet-stream'}

                def on_json(b: bytes):
                    try:
                        j = json.loads(b.decode('utf-8', errors='ignore'))
                        result['transcript'] = j.get('transcript') if isinstance(j, dict) else None
                        result['llm'] = j.get('llm') if isinstance(j, dict) else None
                    except Exception:
                        pass

                def on_audio(b: bytes, ct: str):
                    audio['buf'] = b
                    audio['ctype'] = ct

                parse_multipart(resp, on_json, on_audio)

                user_text = (result.get('transcript') or {}).get('text') if isinstance(result.get('transcript'), dict) else ''
                assist_text = result.get('llm') or ''
                if user_text:
                    print('You:', user_text)
                if assist_text:
                    print('Assistant:', assist_text)
                else:
                    print('Assistant: (no text)')

                if audio.get('buf') and not args.no_play:
                    save_and_play(audio['buf'], audio.get('ctype', 'application/octet-stream'))
        except urllib.error.HTTPError as e:
            print('Server error:', e.read().decode('utf-8', errors='ignore'))
        except Exception as e:
            print('Error:', e)


if __name__ == '__main__':
    main()
