#!/usr/bin/env python3
import argparse
import io
import json
import queue
import shutil
import sys
import time
import urllib.parse
import urllib.request
import wave

try:
    import numpy as np
    import sounddevice as sd
except Exception:
    print("Please install dependencies: pip3 install sounddevice numpy", file=sys.stderr)
    raise


def record_vad(
    samplerate: int = 16000,
    channels: int = 1,
    start_threshold: float = 0.02,
    stop_threshold: float = 0.01,
    min_speech_ms: int = 150,
    trailing_silence_ms: int = 700,
    max_seconds: float = 10.0,
):
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


def record_until_enter(samplerate: int = 16000, channels: int = 1, max_seconds: float = 15.0):
    import threading
    q = queue.Queue()
    collected = []
    stop_evt = threading.Event()

    def cb(indata, frames, time_info, status):
        if status:
            pass
        q.put(indata.copy())

    def wait_enter():
        try:
            input()
        except Exception:
            pass
        stop_evt.set()

    t = threading.Thread(target=wait_enter, daemon=True)
    t.start()

    with sd.InputStream(samplerate=samplerate, channels=channels, dtype='int16', blocksize=1024, callback=cb):
        start = time.time()
        while not stop_evt.is_set():
            try:
                data = q.get(timeout=0.1)
                collected.append(np.frombuffer(data.tobytes(), dtype=np.int16))
            except queue.Empty:
                pass
            if (time.time() - start) >= max_seconds:
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


def build_url(base: str, path: str, params: dict):
    if base.endswith('/'):
        base = base[:-1]
    q = urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, '')})
    return f"{base}{path}?{q}" if q else f"{base}{path}"


def post_llm_tts_audio(base: str, wav_bytes: bytes, session: str, voice: str, llm_model: str, system: str, debug: bool = False):
    url = build_url(base, '/llm_tts', {
        'voice': voice,
        'session': session,
        'llm_model': llm_model,
        'system': system,
        **({'debug': '1'} if debug else {}),
    })
    req = urllib.request.Request(url, data=wav_bytes, headers={'Content-Type': 'audio/wav', 'User-Agent': 'mic-llm-tts/1.0'}, method='POST')
    return urllib.request.urlopen(req)


def play_audio(buf: bytes, ctype: str, pi_mode: bool, alsa_dev: str):
    import tempfile, subprocess
    suffix = '.mp3' if 'mpeg' in (ctype or '') else '.wav'
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
        path = f.name
        f.write(buf)
    print(f'Saved audio to {path}')

    # On Pi prefer ffmpeg->aplay with ALSA device
    if pi_mode:
        aplay = shutil.which('aplay')
        ffmpeg = shutil.which('ffmpeg')
        if aplay and ffmpeg:
            p1 = subprocess.Popen([ffmpeg, '-loglevel', 'error', '-i', path, '-f', 'wav', '-'], stdout=subprocess.PIPE)
            assert p1.stdout is not None
            args = [aplay, '-q'] + (['-D', alsa_dev] if alsa_dev else [])
            subprocess.run(args, stdin=p1.stdout, check=False)
            try:
                p1.stdout.close()
            except Exception:
                pass
            p1.wait()
            return
        mpg = shutil.which('mpg123')
        if mpg:
            subprocess.run([mpg, '-q', path], check=False)
            return

    # macOS default: afplay, otherwise ffplay
    player = shutil.which('afplay') or shutil.which('ffplay')
    if player:
        args = [player]
        if player.endswith('ffplay'):
            args += ['-nodisp', '-autoexit', '-loglevel', 'quiet', path]
        else:
            args += [path]
        subprocess.run(args, check=False)
    else:
        print('No audio player found. Install ffmpeg or mpg123 for playback.', file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description='Record mic and send to /llm_tts (audio-in → Gemini → TTS → audio-out)')
    ap.add_argument('--base', default='http://127.0.0.1:8787', help='Server base URL (default: http://127.0.0.1:8787)')
    ap.add_argument('--session', default='mic', help='Conversation session id (default: mic)')
    ap.add_argument('--voice', default='Joanna', help='TTS voice (default: Joanna)')
    ap.add_argument('--llm-model', default='gemini-2.0-flash', help='Gemini model id (default: gemini-2.0-flash)')
    ap.add_argument('--system', default='', help='Optional system prompt')
    ap.add_argument('--mode', choices=['manual','auto'], default='manual', help='manual: press Enter to stop; auto: VAD stop on silence')
    ap.add_argument('--max-seconds', type=float, default=12.0, help='Max capture length')
    ap.add_argument('--pi', action='store_true', help='Raspberry Pi mode for playback (ALSA aplay)')
    ap.add_argument('--alsa-dev', default='plughw:1,0', help='ALSA device when --pi is set (default: plughw:1,0)')
    ap.add_argument('--debug', action='store_true', help='Append ?debug=1 to server request')
    args = ap.parse_args()

    print(f"Mic → LLM_TTS. Base={args.base} Session={args.session} Voice={args.voice} Model={args.llm_model}")
    print("Press Enter to start recording. Press Enter again to stop (manual mode). Ctrl+C to exit.")

    while True:
        try:
            cmd = input('\nPress Enter to start (or type /quit): ').strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if cmd == '/quit':
            break

        print('Recording… ', end='', flush=True)
        if args.mode == 'manual':
            print('(press Enter to stop)')
            wav = record_until_enter(max_seconds=args.max_seconds)
        else:
            print('(auto-stops on silence)')
            wav = record_vad(max_seconds=args.max_seconds)
        if not wav:
            print('No speech detected; try again.')
            continue
        print(f'Captured {len(wav)} bytes; sending to /llm_tts')

        try:
            with post_llm_tts_audio(args.base, wav, args.session, args.voice, args.llm_model, args.system, args.debug) as resp:
                if resp.status != 200:
                    err = resp.read().decode('utf-8', errors='ignore')
                    print(f'HTTP {resp.status} {resp.reason}:\n{err}', file=sys.stderr)
                    continue
                ctype = resp.getheader('Content-Type') or 'audio/mpeg'
                body = resp.read()
                play_audio(body, ctype, args.pi, args.alsa_dev)
        except urllib.error.HTTPError as e:
            err = e.read().decode('utf-8', errors='ignore')
            print(f'HTTP error: {e.code}\n{err}', file=sys.stderr)
        except Exception as e:
            print(f'Error: {e}', file=sys.stderr)


if __name__ == '__main__':
    main()

