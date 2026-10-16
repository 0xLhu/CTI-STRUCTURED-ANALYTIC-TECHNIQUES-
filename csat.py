#!/usr/bin/env python3
"""
CSAT: CTI Structured Analytic Techniques.

    python csat.py                      open the graphical interface (browser)
    python csat.py session.yaml         open a session in the interface
    python csat.py --cli [--load FILE]  terminal mode
    python csat.py --report FILE        write the Flash Report (Markdown) and exit
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import yaml  # noqa: F401
except ImportError:
    sys.exit("CSAT needs PyYAML:  pip install pyyaml   (Arch: sudo pacman -S python-yaml)")

import csat_core as core


def main():
    p = argparse.ArgumentParser(description="CTI Structured Analytic Techniques")
    p.add_argument("session", nargs="?", help="session YAML to open")
    p.add_argument("--cli", action="store_true", help="interactive terminal mode instead of the GUI")
    p.add_argument("--load", metavar="FILE", help="session to open (same as the positional argument)")
    p.add_argument("--method", metavar="M", help="CLI: jump to ach|kac|iw|da")
    p.add_argument("--report", metavar="FILE", help="write the Flash Report for FILE and exit")
    p.add_argument("--html", action="store_true", help="with --report: write HTML instead of Markdown")
    p.add_argument("--port", type=int, default=8765, help="GUI port (default 8765)")
    p.add_argument("--no-browser", action="store_true", help="GUI: do not open the browser automatically")
    args = p.parse_args()

    path = args.session or args.load

    if args.report:
        try:
            s = core.load_session(args.report)
        except Exception as e:
            sys.exit(f"Could not load {args.report}: {e}")
        out = core.report_filename(s)
        if args.html:
            out = out[:-3] + ".html"
            text = core.report_html(s)
        else:
            text = core.generate_report(s)
        with open(out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"Report written → {out}")
        return

    if path and not os.path.exists(path):
        sys.exit(f"File not found: {path}")

    if args.cli or args.method:
        import csat_cli
        csat_cli.run(path, args.method)
        return

    import csat_gui
    workdir = os.path.dirname(os.path.abspath(path)) if path else os.getcwd()
    csat_gui.run(workdir, path, port=args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
