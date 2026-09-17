#!/usr/bin/env python3
"""
push_theme.py - envia un tema (JSON) a un ThermalEngineLite por HTTP.

Uso:
    python tools/push_theme.py --url http://lite.local:4241 \
        --token secreto --theme "/ruta/Theme.json"

Si el Lite no tiene token, omite --token.
"""

import argparse
import json
import sys
import urllib.error
import urllib.request


def main(argv=None):
    parser = argparse.ArgumentParser(description="Push de un tema a ThermalEngineLite")
    parser.add_argument("--url", required=True,
                        help="URL base de Lite, p.ej. http://host:4241")
    parser.add_argument("--theme", required=True, help="Ruta al JSON del tema")
    parser.add_argument("--token", default=None, help="Token de autenticacion")
    parser.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args(argv)

    with open(args.theme, "r", encoding="utf-8") as f:
        payload = json.load(f)

    body = json.dumps(payload).encode("utf-8")
    endpoint = args.url.rstrip("/") + "/theme"
    req = urllib.request.Request(endpoint, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    if args.token:
        req.add_header("X-Token", args.token)

    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as resp:
            data = resp.read().decode("utf-8", errors="replace")
            print(f"OK {resp.status}: {data}")
            return 0
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        print(f"ERROR {e.code}: {detail}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"No se pudo conectar a {endpoint}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
