#!/usr/bin/env python3
import argparse
import io
import json
import os
import queue
import shutil
import sys
import tempfile
import time
import wave
import urllib.parse
import urllib.request

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
    Stream audio from default input and capture from first speech onset
    until trailing silence or max_seconds. Thresholds are relative (0..1) of int16.
    Returns bytes of PCM16 mono at samplerate.
    """
    q = queue.Queue()
    started = False
    speech_start_ts = None
    last_voice_ts = None
    collected = []

    blocksize = 1024
    max_samples = int(max_seconds * samplerate)
    silence_limit_samples = int(trailing_silence_ms * samplerate / 1000)
    min_speech_samples = int(min_speech_ms * samplerate / 1000)

    scale = 32768.0

    def cb(indata, frames, time_info, status):
        if status:
            # print(status, file=sys.stderr)
            pass
        q.put(indata.copy())

    with sd.InputStream(samplerate=samplerate, channels=channels, dtype='int16', blocksize=blocksize, callback=cb):
        start_time = time.time()
        total_samples = 0
        while True:
            try:
                data = q.get(timeout=0.5)
            except queue.Empty:
                if started:
                    # timeout while started counts as silence
                    if (time.time() - last_voice_ts) * samplerate > silence_limit_samples:
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
                    # still waiting for speech
                    continue
            else:
                collected.append(x)
                # Update last voice time
                if level >= stop_threshold:
                    last_voice_ts = time.time()

                # Check for trailing silence and min speech duration
                speech_dur_samples = int((time.time() - speech_start_ts) * samplerate)
                since_voice_samples = int((time.time() - last_voice_ts) * samplerate)
                if speech_dur_samples >= min_speech_samples and since_voice_samples >= silence_limit_samples:
                    break

            if total_samples >= max_samples:
                break

    if not collected:
        return b""
    y = np.concatenate(collected).astype(np.int16)
    # Serialize to WAV in-memory
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(samplerate)
        wf.writeframes(y.tobytes())
    return buf.getvalue()


def post_audio(base: str, wav_bytes: bytes, return_mode: str, voice: str):
    url = build_url(base, "/transcribe", {"return": return_mode, "voice": voice} if return_mode == 'tts' else {"return": return_mode})
    req = urllib.request.Request(url, data=wav_bytes, headers={"Content-Type": "audio/wav", "User-Agent": "waifu-mic/1.0"}, method='POST')
    return urllib.request.urlopen(req)


def build_url(base: str, p: str, params: dict):
    if base.endswith('/'):
        base = base[:-1]
    q = urllib.parse.urlencode(params)
    return f"{base}{p}?{q}" if q else f"{base}{p}"


def save_and_optionally_play(audio_bytes: bytes, play: bool):
    with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as f:
        path = f.name
        f.write(audio_bytes)
    print(f"Saved audio to {path}")
    if play:
        player = shutil.which('ffplay') or shutil.which('afplay')
        if player:
            import subprocess
            args = [player]
            if os.path.basename(player) == 'ffplay':
                args += ['-nodisp', '-autoexit', '-loglevel', 'quiet', path]
            else:
                args += [path]
            subprocess.run(args, check=False)
        else:
            print("No audio player found (ffplay/afplay)")


def main():
    ap = argparse.ArgumentParser(description='Record from mic, send to /transcribe, and print transcript')
    ap.add_argument('--base', default='http://127.0.0.1:8787', help='Base server URL')
    ap.add_argument('--return', dest='ret', choices=['original', 'tts', 'none', 'llm_tts'], default='original', help='Audio part to return')
    ap.add_argument('--voice', default='Brian', help='Voice if return=tts or llm_tts')
    ap.add_argument('--session', default='mic', help='Conversation session id for llm_tts')
    # Leave blank to use server default (HF Mistral v0.2)
    ap.add_argument('--llm-model', default='', help='LLM model for llm_tts (e.g., mistralai/Mistral-7B-Instruct-v0.2)')
    ap.add_argument('--system', default='', help='Optional system prompt for llm_tts')
    ap.add_argument('--max-seconds', type=float, default=10.0, help='Max capture length')
    ap.add_argument('--play', action='store_true', help='Play returned audio part')
    args = ap.parse_args()

    say('Waiting for audio')
    print('Waiting for audio… start speaking (auto-stops on silence)')
    wav_bytes = record_from_mic(max_seconds=args.max_seconds)
    if not wav_bytes:
        print('No speech detected.')
        return
    say('Got it')
    print(f'Captured {len(wav_bytes)} bytes of WAV; posting to /transcribe')

    # append llm params to URL if needed by building query in post_audio
    def post_with_params():
        params = {"return": args.ret}
        if args.ret == 'tts':
            params.update({"voice": args.voice})
        elif args.ret == 'llm_tts':
            params.update({"voice": args.voice, "llm_model": args.llm_model, "system": args.system, "session": args.session})
        url = build_url(args.base, "/transcribe", params)
        req = urllib.request.Request(url, data=wav_bytes, headers={"Content-Type": "audio/wav", "User-Agent": "waifu-mic/1.0"}, method='POST')
        return urllib.request.urlopen(req)

    try:
        with post_with_params() as resp:
            if resp.status != 200:
                print(f'HTTP {resp.status} {resp.reason}', file=sys.stderr)
                print(resp.read().decode('utf-8', errors='ignore'))
                return
            ctype = resp.getheader('Content-Type') or ''
            body = resp.read()
            if 'multipart/mixed' in ctype:
                # naive split just to print JSON quickly
                try:
                    parts = body.split(b"\r\n\r\n", 2)
                    if len(parts) >= 2:
                        json_start = parts[1]
                        # find end of json by first boundary indicator
                        end_idx = json_start.find(b"\r\n--")
                        if end_idx != -1:
                            j = json.loads(json_start[:end_idx].decode('utf-8', errors='ignore'))
                            print('Transcript:')
                            print(json.dumps(j, indent=2))
                except Exception:
                    pass
                # Optionally save whole body for inspection
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.bin')
                tmp.write(body)
                tmp.close()
                print(f'Saved multipart to {tmp.name}')
            else:
                print(body.decode('utf-8', errors='ignore'))
    except urllib.error.HTTPError as e:
        err = e.read().decode('utf-8', errors='ignore')
        print(f'HTTP {e.code} error from /transcribe:\n{err}', file=sys.stderr)


if __name__ == '__main__':
    main()
