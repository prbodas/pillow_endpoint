#!/usr/bin/env python3
import argparse
import io
import json
import os
import queue
import re
import shutil
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import wave

try:
    import numpy as np
    import sounddevice as sd
except Exception as e:
    print("Please install dependencies: pip3 install sounddevice numpy", file=sys.stderr)
    raise


def say(text: str):
    cmd = shutil.which("say")
    if cmd:
        try:
            import subprocess
            subprocess.run([cmd, text], check=False)
        except Exception:
            pass


def record_from_mic(
    samplerate: int = 16000,
    channels: int = 1,
    start_threshold: float = 0.02,
    stop_threshold: float = 0.01,
    min_speech_ms: int = 150,
    trailing_silence_ms: int = 700,
    max_seconds: float = 10.0,
):
    """
    Capture a single utterance from the default microphone.
    Starts when audio crosses start_threshold and stops after trailing silence.
    Returns bytes of WAV (PCM16 mono at samplerate) or b'' if nothing captured.
    """
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
    q = urllib.parse.urlencode(params)
    return f"{base}{p}?{q}" if q else f"{base}{p}"


def parse_multipart(resp, on_json, on_audio):
    """Parse multipart/mixed by buffering the whole body and splitting by boundary.
    Robust when parts omit Content-Length.
    """
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


def save_and_play(audio_bytes: bytes, ctype: str, play: bool):
    suffix = '.mp3' if 'mpeg' in ctype else '.wav'
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
        out = f.name
        f.write(audio_bytes)
    print(f"Saved audio to {out}")
    if not play:
        return
    player = shutil.which('ffplay') or shutil.which('afplay')
    if not player:
        print("No audio player found. Install ffmpeg or use afplay on macOS.", file=sys.stderr)
        return
    import subprocess
    args = [player]
    if os.path.basename(player) == 'ffplay':
        args += ['-nodisp', '-autoexit', '-loglevel', 'quiet', out]
    else:
        args += [out]
    subprocess.run(args, check=False)


def convo_once(base: str, session: str, voice: str, llm_model: str, system: str, wav_bytes: bytes):
    params = {"return": "llm_tts", "voice": voice, "session": session}
    if llm_model:
        params["llm_model"] = llm_model
    if system:
        params["system"] = system
    url = build_url(base, "/transcribe", params)
    req = urllib.request.Request(url, data=wav_bytes, headers={"Content-Type": "audio/wav", "User-Agent": "mic-convo/1.0"}, method='POST')
    with urllib.request.urlopen(req) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} {resp.reason}")
        ctype = resp.getheader('Content-Type') or ''
        if 'multipart/mixed' not in ctype:
            body = resp.read().decode('utf-8', errors='ignore')
            return {"transcript": None, "assistant": None, "raw": body}, {"buf": None, "ctype": ''}
        result = {"transcript": None, "assistant": None}

        def on_json(b: bytes):
            try:
                j = json.loads(b.decode('utf-8', errors='ignore'))
                result["transcript"] = j
                # If server includes 'llm', capture it
                if isinstance(j, dict) and 'llm' in j and isinstance(j['llm'], str):
                    result["assistant"] = j['llm']
            except Exception:
                pass

        audio_bin = {"buf": None, "ctype": "application/octet-stream"}

        def on_audio(b: bytes, ct: str):
            audio_bin["buf"] = b
            audio_bin["ctype"] = ct

        parse_multipart(resp, on_json, on_audio)
        return result, audio_bin


def _record_until_event(stop_evt, samplerate: int = 16000, channels: int = 1, max_seconds: float = 15.0):
    q = queue.Queue()
    collected = []

    def cb(indata, frames, time_info, status):
        if status:
            pass
        q.put(indata.copy())

    start = time.time()
    with sd.InputStream(samplerate=samplerate, channels=channels, dtype='int16', blocksize=1024, callback=cb):
        while not stop_evt.is_set():
            try:
                data = q.get(timeout=0.1)
                collected.append(np.frombuffer(data.tobytes(), dtype=np.int16))
            except queue.Empty:
                pass
            if (time.time() - start) >= max_seconds:
                break
    if not collected:
        return b''
    y = np.concatenate(collected).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(samplerate)
        wf.writeframes(y.tobytes())
    return buf.getvalue()


def main():
    ap = argparse.ArgumentParser(description='Hands-free voice chat with LLM + TTS, with session history')
    ap.add_argument('--base', default='http://127.0.0.1:8787', help='Base server URL')
    ap.add_argument('--session', default='voice', help='Conversation session id')
    ap.add_argument('--voice', default='Joanna', help='TTS voice (female). Examples: Joanna, Amy, Salli, Nicole')
    ap.add_argument('--llm-model', default='', help='LLM model override (server default if empty)')
    ap.add_argument('--system', default='', help='Optional system prompt')
    ap.add_argument('--max-seconds', type=float, default=15.0, help='Max capture length per turn')
    ap.add_argument('--mode', choices=['manual','auto'], default='manual', help='manual: press Enter to stop; auto: VAD stop on silence')
    ap.add_argument('--no-play', action='store_true', help='Do not play returned audio')
    args = ap.parse_args()

    print(f"Voice chat ready. Session={args.session} Voice={args.voice}")
    print("Commands: press Enter to speak, '/reset' to clear history, '/quit' to exit, '/voice Name' to change voice.")

    while True:
        try:
            cmd = input('\nPress Enter to speak (or type a command): ').strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if cmd == '/quit':
            break
        if cmd.startswith('/voice'):
            parts = cmd.split(None, 1)
            if len(parts) == 2 and parts[1].strip():
                args.voice = parts[1].strip()
                print(f"Voice set to: {args.voice}")
            else:
                print("Usage: /voice <Name>")
            continue
        if cmd == '/reset':
            # hit /llm with reset flag to clear server-side history
            try:
                url = build_url(args.base, '/llm', {"session": args.session, "reset": '1'})
                data = json.dumps({"text": ""}).encode('utf-8')
                req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json', 'User-Agent': 'mic-convo/1.0'})
                urllib.request.urlopen(req).read()
            except Exception:
                pass
            print('(history cleared)')
            continue

        import threading
        say('Listening')
        if args.mode == 'manual':
            print('Recording… press Enter to stop')
            stop_evt = threading.Event()

            def wait_enter():
                try:
                    input()
                except Exception:
                    pass
                stop_evt.set()

            t = threading.Thread(target=wait_enter, daemon=True)
            t.start()
            wav = _record_until_event(stop_evt, max_seconds=args.max_seconds)
        else:
            print('Speak now… (auto-stops on silence)')
            wav = record_from_mic(max_seconds=args.max_seconds)
        if not wav:
            print('No speech detected; try again.')
            continue

        say('Got it')
        try:
            result, audio = convo_once(args.base, args.session, args.voice, args.llm_model, args.system, wav)
        except urllib.error.HTTPError as e:
            err = e.read().decode('utf-8', errors='ignore')
            print(f'HTTP {e.code} error from /transcribe:\n{err}', file=sys.stderr)
            continue
        except Exception as e:
            print(f'Error: {e}', file=sys.stderr)
            continue

        # Show transcript text (user) and assistant text if provided
        t = (result or {}).get('transcript') or {}
        user_text = (t.get('text') if isinstance(t, dict) else None) or t
        if user_text:
            print(f'You: {user_text}')
        assistant_text = (result or {}).get('assistant')
        if assistant_text:
            print(f'Assistant: {assistant_text}')
        else:
            print('Assistant: (no text in JSON part)')

        if audio.get('buf'):
            save_and_play(audio['buf'], audio.get('ctype', 'application/octet-stream'), not args.no_play)
        else:
            print('No audio returned (TTS or parsing issue). See Assistant text above.')


if __name__ == '__main__':
    main()
