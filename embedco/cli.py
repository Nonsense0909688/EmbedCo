"""Command-line entry points: ``serve`` (the editor) and ``build`` (sketch generator)."""

import argparse
import json
import logging
import sys
from pathlib import Path

from . import __version__
from .errors import BlockError
from .generator import EmbedCoGenerator
from .logging_config import configure_logging
from .settings import Settings

logger = logging.getLogger(__name__)

EXAMPLES = {
    "distance_servo": {
        "board": "uno",
        "loop": [{
            "type": "if",
            "inputs": {"condition": {"type": "less", "inputs": {
                "a": {"type": "read_distance", "inputs": {"trigger_pin": 9, "echo_pin": 10}},
                "b": 20}}},
            "then": [{"type": "servo_move", "inputs": {"pin": 6, "angle": 90}}],
            "else": [{"type": "servo_move", "inputs": {"pin": 6, "angle": 0}}],
        }],
    },
    "blink": {
        "board": "uno",
        "loop": [
            {"type": "digital_write", "inputs": {"pin": 13, "state": True}},
            {"type": "wait", "inputs": {"milliseconds": 500}},
            {"type": "digital_write", "inputs": {"pin": 13, "state": False}},
            {"type": "wait", "inputs": {"milliseconds": 500}},
        ],
    },
}


def serve_main(argv=None):
    from .web.app import serve

    parser = argparse.ArgumentParser(prog="server.py", description="EmbedCo visual editor")
    parser.add_argument("--host", help="bind address (default 127.0.0.1)")
    parser.add_argument("--port", type=int, help="bind port (default 8000)")
    parser.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    parser.add_argument("--log-format", choices=["text", "json"])
    parser.add_argument("--version", action="version", version=f"EmbedCo {__version__}")
    args = parser.parse_args(argv)

    try:
        settings = Settings.from_env(
            host=args.host, port=args.port,
            log_level=args.log_level, log_format=args.log_format,
        )
    except ValueError as error:
        parser.error(str(error))

    configure_logging(settings)
    try:
        serve(settings, open_browser=not args.no_browser)
    except OSError as error:
        logger.critical("Could not start server on %s:%s: %s", settings.host, settings.port, error)
        return 1
    except Exception:
        logger.critical("Server crashed", exc_info=True)
        return 1
    return 0


def build_main(argv=None):
    parser = argparse.ArgumentParser(prog="main.py", description="Build Arduino sketches from EmbedCo projects")
    parser.add_argument("project", nargs="?", type=Path, help="project JSON exported from the editor (default: built-in examples)")
    parser.add_argument("--board", help="override the project's board")
    parser.add_argument("--out", type=Path, default=Path("output"), help="output directory (default ./output)")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default=None)
    args = parser.parse_args(argv)

    settings = Settings.from_env(log_level=args.log_level or "WARNING", log_to_file=False)
    configure_logging(settings)

    generator = EmbedCoGenerator(
        definitions=settings.blocks_dir, boards=settings.boards_file, plugins_dir=settings.plugins_dir,
    )

    if args.project:
        try:
            projects = {args.project.stem: json.loads(args.project.read_text(encoding="utf-8"))}
        except (OSError, ValueError) as error:
            logger.error("Cannot read project %s: %s", args.project, error)
            print(f"error: cannot read {args.project}: {error}", file=sys.stderr)
            return 2
    else:
        projects = EXAMPLES

    try:
        args.out.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        print(f"error: cannot create {args.out}: {error}", file=sys.stderr)
        return 2

    failures = 0
    for name, project in projects.items():
        if args.board and isinstance(project, dict):
            project = {**project, "board": args.board}
        try:
            code = generator.generate_project(project)
        except (BlockError, KeyError, TypeError, AttributeError) as error:
            failures += 1
            logger.error("Build failed for %s: %s", name, error)
            print(f"error: {name}: {error}", file=sys.stderr)
            continue
        target = args.out / f"{name}.ino"
        target.write_text(code, encoding="utf-8")
        for warning in generator.warnings:
            print(f"warning: {name}: {warning}", file=sys.stderr)
        print(f"wrote {target}")
    return 1 if failures else 0
