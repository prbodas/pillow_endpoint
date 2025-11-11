#!/usr/bin/env python3
import argparse
import json
import sys
import urllib.request
import urllib.parse


def post_llm(base: str, text: str, session: str, model: str, system: str, reset: bool):
    if base.endswith('/'):
        base = base[:-1]
    params = {}
    if session:
        params['session'] = session
    if model:
        params['llm_model'] = model
    if system:
        params['system'] = system
    if reset:
        params['reset'] = '1'
    url = f"{base}/llm"
    if params:
        url += '?' + urllib.parse.urlencode(params)
    data = json.dumps({'text': text}).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json', 'User-Agent': 'llm-cli/1.0'})
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read()
            try:
                return json.loads(body.decode('utf-8'))
            except Exception:
                return {'ok': False, 'raw': body.decode('utf-8', errors='ignore')}
    except urllib.error.HTTPError as e:
        err = e.read().decode('utf-8', errors='ignore')
        try:
            return json.loads(err)
        except Exception:
            return {'ok': False, 'status': e.code, 'error': err}


def interactive(base: str, session: str, model: str, system: str):
    print(f"Interactive chat. Session={session} Model={model}")
    print("Type '/reset' to clear, '/quit' to exit.")
    while True:
        try:
            text = input('You> ').strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            continue
        if text == '/quit':
            break
        if text == '/reset':
            post_llm(base, '', session, model, system, True)
            print('(history cleared)')
            continue
        res = post_llm(base, text, session, model, system, False)
        reply = res.get('reply')
        if reply:
            print('Assistant>', reply)
        else:
            print('Assistant> (no reply)')
            try:
                print(json.dumps(res, indent=2))
            except Exception:
                pass


def main():
    ap = argparse.ArgumentParser(description='Talk to the server-side LLM with conversation history')
    ap.add_argument('--base', default='http://127.0.0.1:8787', help='Base server URL')
    ap.add_argument('--session', default='cli', help='Conversation session id')
    # Leave blank to let the server choose a safe default.
    ap.add_argument('--model', default='', help='LLM model id (e.g., mistralai/Mistral-7B-Instruct-v0.2)')
    ap.add_argument('--system', default='', help='Optional system prompt')
    ap.add_argument('--text', default='', help='One-shot text. If omitted, starts interactive mode')
    ap.add_argument('--reset', action='store_true', help='Reset session history before sending')
    args = ap.parse_args()

    if args.text:
        res = post_llm(args.base, args.text, args.session, args.model, args.system, args.reset)
        print(json.dumps(res, indent=2))
    else:
        interactive(args.base, args.session, args.model, args.system)


if __name__ == '__main__':
    main()
