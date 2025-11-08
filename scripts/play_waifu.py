#!/usr/bin/env python3
import argparse
import os
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import shutil
import subprocess
import uuid
import io


def detect_ffplay():
    path = shutil.which("ffplay")
    return path


def detect_afplay():
    path = shutil.which("afplay")
    return path


def fetch_bytes(url: str, chunk_size: int = 16384) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "waifu-client/1.0"})
    with urllib.request.urlopen(req) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status}: {resp.reason}")
        data = bytearray()
        while True:
            chunk = resp.read(chunk_size)
            if not chunk:
                break
            data.extend(chunk)
        return bytes(data)


def play_bytes(audio_bytes: bytes, suffix: str = ".mp3") -> None:
    ff = detect_ffplay()
    af = detect_afplay()
    if not ff and not af:
        print("No audio player found. Install ffmpeg (ffplay) or use macOS afplay.", file=sys.stderr)
        sys.exit(2)
    player = ff or af
    base_args = ["-nodisp", "-autoexit", "-loglevel", "quiet"] if ff else []
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
        path = f.name
        f.write(audio_bytes)
    try:
        args = [player] + base_args
        if ff:
            args += [path]
        else:
            args += [path]
        subprocess.run(args, check=False)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def build_url(base: str, path: str, params: dict) -> str:
    if base.endswith("/"):
        base = base[:-1]
    qp = urllib.parse.urlencode(params)
    return f"{base}{path}?{qp}" if qp else f"{base}{path}"


def stream_to_player(url: str, read_chunk: int = 32 * 1024):
    ff = detect_ffplay()
    af = detect_afplay()
    if not ff and not af:
        print("No audio player found. Install ffmpeg (ffplay) or use macOS afplay.", file=sys.stderr)
        sys.exit(2)

    req = urllib.request.Request(url, headers={"User-Agent": "waifu-client/1.0"})
    with urllib.request.urlopen(req) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status}: {resp.reason}")

        if ff:
            # Stream into ffplay stdin
            proc = subprocess.Popen([ff, "-nodisp", "-autoexit", "-loglevel", "quiet", "-i", "-"], stdin=subprocess.PIPE)
            try:
                while True:
                    chunk = resp.read(read_chunk)
                    if not chunk:
                        break
                    assert proc.stdin is not None
                    proc.stdin.write(chunk)
                if proc.stdin:
                    proc.stdin.close()
                proc.wait()
            finally:
                if proc.poll() is None:
                    proc.kill()
        else:
            # Fallback: buffer to a temp file then play with afplay (not truly real-time).
            # Note: afplay is unreliable with FIFOs for MP3; buffering avoids 'AudioFileOpen failed'.
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
                path = f.name
                total = 0
                while True:
                    chunk = resp.read(read_chunk)
                    if not chunk:
                        break
                    f.write(chunk)
                    total += len(chunk)
                    if total % (256 * 1024) < read_chunk:
                        print(f"  downloaded ~{total//1024} KiB", file=sys.stderr)
            try:
                subprocess.run([af, path], check=False)
            finally:
                try:
                    os.remove(path)
                except OSError:
                    pass


def parse_multipart_stream(resp, boundary: str, write_bytes):
    bline = ("--" + boundary).encode("utf-8")
    end_marker = ("--" + boundary + "--").encode("utf-8")
    # Read helper
    def readline() -> bytes:
        return resp.readline()

    # Consume until first boundary
    while True:
        line = readline()
        if not line:
            return
        if line.strip() == bline:
            break

    while True:
        # Read headers
        headers = {}
        while True:
            line = readline()
            if not line:
                return
            if line in (b"\r\n", b"\n"):
                break
            key, _, val = line.decode("utf-8", errors="ignore").partition(":")
            headers[key.lower().strip()] = val.strip()

        length = int(headers.get("content-length", "0"))
        remaining = length
        while remaining > 0:
            chunk = resp.read(min(remaining, 64 * 1024))
            if not chunk:
                return
            write_bytes(chunk)
            remaining -= len(chunk)

        # CRLF after part
        _ = resp.read(2)

        # Next boundary
        line = readline()
        if not line:
            return
        if line.strip() == end_marker:
            return
        if line.strip() != bline:
            # Malformed, stop
            return


def stream_multipart_to_player(url: str):
    ff = detect_ffplay()
    af = detect_afplay()
    if not ff and not af:
        print("No audio player found. Install ffmpeg (ffplay) or use macOS afplay.", file=sys.stderr)
        sys.exit(2)

    req = urllib.request.Request(url, headers={"User-Agent": "waifu-client/1.0"})
    with urllib.request.urlopen(req) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status}: {resp.reason}")
        ctype = resp.getheader("Content-Type") or ""
        boundary = None
        if "boundary=" in ctype:
            boundary = ctype.split("boundary=", 1)[1].strip()
        if not boundary:
            raise RuntimeError("Missing multipart boundary")

        if ff:
            proc = subprocess.Popen([ff, "-nodisp", "-autoexit", "-loglevel", "quiet", "-i", "-"], stdin=subprocess.PIPE)
            try:
                def write_bytes(b: bytes):
                    assert proc.stdin is not None
                    proc.stdin.write(b)
                parse_multipart_stream(resp, boundary, write_bytes)
                if proc.stdin:
                    proc.stdin.close()
                proc.wait()
            finally:
                if proc.poll() is None:
                    proc.kill()
        else:
            # Buffer all parts into a single temp file and play with afplay
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
                path = f.name
                def write_bytes(b: bytes):
                    f.write(b)
                parse_multipart_stream(resp, boundary, write_bytes)
            try:
                subprocess.run([af, path], check=False)
            finally:
                try:
                    os.remove(path)
                except OSError:
                    pass


def run_stream_loop(base: str, text: str, voice: str, parts: int, delay: float, chunk: int, gap: int, read_chunk: int, server_parts: int, partgap: int, multipart: bool):
    print(f"Streaming loop: {parts} call(s) — server_parts={server_parts} — multipart={multipart} — text=\"{text}\" voice={voice} chunk={chunk} gap={gap}ms partgap={partgap}ms")
    for i in range(1, parts + 1):
        url = build_url(base, "/tts", {
            "stream": "true",
            "text": text,
            "voice": voice,
            # server-side multi-part in a single stream
            "parts": str(server_parts),
            "chunk": str(chunk),
            "gap": str(gap),
            "partgap": str(partgap),
            **({"multipart": "1"} if multipart else {}),
        })
        print(f"[part {i}] streaming {url}")
        if multipart:
            stream_multipart_to_player(url)
        else:
            stream_to_player(url, read_chunk=read_chunk)
        if i != parts and delay > 0:
            time.sleep(delay)


def run_non_stream(base: str, text: str, voice: str):
    url = build_url(base, "/tts", {
        "stream": "false",
        "text": text,
        "voice": voice,
    })
    print(f"Non-stream fetch: {url}")
    audio = fetch_bytes(url)
    print(f"Received {len(audio)} bytes — playing…")
    play_bytes(audio)


def main():
    parser = argparse.ArgumentParser(description="Play TTS from the worker — streaming loop and non-stream modes.")
    parser.add_argument("--base", default="http://127.0.0.1:8787", help="Base URL of the worker (default: http://127.0.0.1:8787)")
    parser.add_argument("--text", default="I love my waifu", help="Text to synthesize")
    parser.add_argument("--voice", default="Brian", help="Voice id/name")
    parser.add_argument("--parts", type=int, default=1, help="Number of streaming parts to loop through")
    parser.add_argument("--delay", type=float, default=0.15, help="Delay between streaming parts (seconds)")
    parser.add_argument("--nonstream-first", action="store_true", help="Play non-stream sample before the streaming loop")
    parser.add_argument("--chunk", type=int, default=32768, help="Bytes per chunk in server-side mock stream")
    parser.add_argument("--gap", type=int, default=20, help="Delay (ms) between chunks in server-side mock stream")
    parser.add_argument("--server-parts", type=int, default=1, help="Number of parts to include in one streaming response")
    parser.add_argument("--partgap", type=int, default=150, help="Delay (ms) between parts in one streaming response")
    parser.add_argument("--read-chunk", type=int, default=32768, help="Client read size in bytes for streaming")
    parser.add_argument("--multipart", action="store_true", help="Use HTTP multipart/mixed response with N parts in one stream")
    args = parser.parse_args()

    if args.nonstream_first:
        run_non_stream(args.base, args.text, args.voice)

    run_stream_loop(args.base, args.text, args.voice, args.parts, args.delay, args.chunk, args.gap, args.read_chunk, args.server_parts, args.partgap, args.multipart)

    if not args.nonstream_first:
        run_non_stream(args.base, args.text, args.voice)


if __name__ == "__main__":
    main()
