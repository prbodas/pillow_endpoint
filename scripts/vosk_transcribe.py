#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
import tempfile
import wave


def ensure_wav_16k_mono(src_path: str) -> str:
    # Convert input to 16kHz mono WAV PCM using ffmpeg
    out_fd, out_path = tempfile.mkstemp(suffix=".wav")
    os.close(out_fd)
    cmd = [
        "ffmpeg", "-nostdin", "-y",
        "-i", src_path,
        "-ar", "16000",
        "-ac", "1",
        "-f", "wav",
        out_path,
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        try:
            os.remove(out_path)
        except OSError:
            pass
        raise RuntimeError(f"ffmpeg convert failed: {e}")
    return out_path


def transcribe(model_dir: str, wav_path: str) -> dict:
    try:
        from vosk import Model, KaldiRecognizer
    except Exception as e:
        raise RuntimeError("vosk not installed. pip install vosk") from e

    wf = wave.open(wav_path, "rb")
    if wf.getnchannels() != 1 or wf.getsampwidth() != 2 or wf.getframerate() != 16000:
        wf.close()
        raise RuntimeError("WAV must be 16kHz mono PCM16")

    model = Model(model_dir)
    rec = KaldiRecognizer(model, wf.getframerate())
    rec.SetWords(True)

    results = []
    while True:
        data = wf.readframes(4000)
        if len(data) == 0:
            break
        if rec.AcceptWaveform(data):
            part = rec.Result()
            results.append(json.loads(part))
    final = json.loads(rec.FinalResult())
    wf.close()

    # Collate transcript
    words = []
    text_parts = []
    for r in results + [final]:
        if 'text' in r:
            text_parts.append(r['text'])
        if 'result' in r:
            words.extend(r['result'])
    text = ' '.join([t for t in text_parts if t]).strip()
    return {"text": text, "words": words}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="Path to Vosk model directory")
    ap.add_argument("--input", required=True, help="Input audio file path")
    args = ap.parse_args()

    wav = ensure_wav_16k_mono(args.input)
    try:
        result = transcribe(args.model, wav)
        print(json.dumps(result))
    finally:
        try:
            os.remove(wav)
        except OSError:
            pass


if __name__ == "__main__":
    main()

