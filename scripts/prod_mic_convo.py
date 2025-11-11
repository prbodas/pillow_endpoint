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


def main():
    ap = argparse.ArgumentParser(description='Prod mic client — all compute on server via /transcribe?return=llm_tts')
    ap.add_argument('--base', default=os.environ.get('AI_BASE', 'https://<your-ai-service>.onrender.com'), help='AI server base URL')
    ap.add_argument('--session', default='prod', help='Conversation session id')
    ap.add_argument('--voice', default='Joanna', help='TTS voice')
    ap.add_argument('--llm-model', default='gemini-2.0-flash', help='Gemini model id')
    ap.add_argument('--system', default='', help='Optional system prompt')
    ap.add_argument('--max-seconds', type=float, default=12.0, help='Max capture length per turn')
    ap.add_argument('--no-play', action='store_true', help='Do not play returned audio')
    args = ap.parse_args()

    print(f"Prod mic ready. Base={args.base} Session={args.session} Voice={args.voice}")
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
                body = resp.read()
                if 'multipart/mixed' not in ctype:
                    print(body.decode('utf-8', errors='ignore'))
                    continue
                # Parse minimally: split parts and extract JSON + audio
                try:
                    head, json_and_rest = body.split(b"\r\n\r\n", 1)
                    json_blob, rest = json_and_rest.split(b"\r\n--", 1)
                    j = json.loads(json_blob.decode('utf-8', errors='ignore'))
                    print('You:', (j.get('transcript') or {}).get('text', ''))
                    print('Assistant:', j.get('llm') or '')
                except Exception:
                    pass
                if args.no_play:
                    continue
                # Save entire body for external playback if needed
                tmp = os.path.join(os.getcwd(), f"prod_reply_{int(time.time())}.bin")
                try:
                    with open(tmp, 'wb') as f:
                        f.write(body)
                    print('Saved multipart to', tmp)
                except Exception:
                    pass
        except urllib.error.HTTPError as e:
            print('Server error:', e.read().decode('utf-8', errors='ignore'))
        except Exception as e:
            print('Error:', e)


if __name__ == '__main__':
    main()

