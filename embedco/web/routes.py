"""API routes. Handlers take a Request and return (status, payload) or a Response."""

import logging
from dataclasses import dataclass
from urllib.parse import unquote

from .. import __version__
from ..errors import NotFoundError, ValidationError
from ..services.arduino import ArduinoService
from ..services.codegen import CodegenService
from ..services.projects import ProjectStore
from ..services.terminal import TerminalService
from ..settings import Settings
from .router import Response, Router

logger = logging.getLogger(__name__)


@dataclass
class Services:
    settings: Settings
    codegen: CodegenService
    projects: ProjectStore
    arduino: ArduinoService
    terminal: TerminalService


def build_router(svc):
    router = Router()

    # ---- UI + health ----

    def index(req):
        try:
            return Response(200, svc.settings.ui_file.read_bytes(), "text/html")
        except OSError:
            logger.error("UI file missing: %s", svc.settings.ui_file)
            raise NotFoundError("Editor UI not found") from None

    router.add("GET", "/", index)
    router.add("GET", "/index.html", index)

    @router.route("GET", "/logo.svg")
    def logo(req):
        logo_file = svc.settings.ui_file.parent / "logo.svg"
        try:
            return Response(200, logo_file.read_bytes(), "image/svg+xml")
        except OSError:
            logger.error("Logo file missing: %s", logo_file)
            raise NotFoundError("Logo not found") from None

    @router.route("GET", "/healthz")
    def health(req):
        return 200, {
            "status": "ok",
            "version": __version__,
            "arduino_cli": bool(svc.arduino.cli_path()),
            "terminal": svc.terminal.enabled,
        }

    # ---- palette / boards / ports ----

    @router.route("GET", "/api/palette")
    def palette(req):
        return 200, {"palette": svc.codegen.palette(), "boards": svc.codegen.boards()}

    @router.route("GET", "/api/ports")
    def ports(req):
        return 200, {"ports": svc.arduino.list_ports()}

    # ---- examples ----

    @router.route("GET", "/api/examples")
    def examples_list(req):
        import json
        out = []
        exdir = svc.settings.examples_dir
        if exdir.is_dir():
            for path in sorted(exdir.glob("*.json")):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    logger.warning("Skipping invalid example: %s", path)
                    continue
                if not isinstance(data, dict):
                    continue
                out.append({
                    "id": path.stem,
                    "name": str(data.get("name") or path.stem),
                    "description": str(data.get("description") or ""),
                    "board": str(data.get("board") or "uno"),
                })
        return 200, {"examples": out}

    @router.route("GET", "/api/examples/<example_id>")
    def examples_get(req):
        import json, re
        example_id = unquote(req.params["example_id"])
        if not re.fullmatch(r"[A-Za-z0-9._-]+", example_id):
            raise ValidationError("Invalid example id")
        path = svc.settings.examples_dir / f"{example_id}.json"
        try:
            resolved = path.resolve()
            resolved.relative_to(svc.settings.examples_dir.resolve())
        except Exception:
            raise NotFoundError("Example not found") from None
        if not resolved.is_file():
            raise NotFoundError("Example not found")
        try:
            data = json.loads(resolved.read_text(encoding="utf-8"))
        except Exception:
            raise ValidationError("Example file is not valid JSON") from None
        if not isinstance(data, dict):
            raise ValidationError("Example file is not valid")
        data.setdefault("name", example_id)
        data.setdefault("board", "uno")
        return 200, {"id": example_id, "project": data}

    # ---- plugins ----

    @router.route("GET", "/api/plugins")
    def plugins_list(req):
        return 200, {"plugins": svc.codegen.list_plugins()}

    @router.route("POST", "/api/plugins/install")
    def plugins_install(req):
        body = req.json()
        data = body.get("plugin")
        if data is None:
            content = body.get("content")
            if isinstance(content, str):
                import json
                try:
                    data = json.loads(content)
                except ValueError:
                    raise ValidationError("Plugin JSON is not valid.") from None
            else:
                data = content
        meta = svc.codegen.install_plugin(data, body.get("filename") or "plugin")
        return 201, {"ok": True, "plugin": meta}

    @router.route("POST", "/api/plugins/<plugin_id>/toggle")
    def plugins_toggle(req):
        plugin_id = unquote(req.params["plugin_id"])
        enabled = bool(req.json().get("enabled", True))
        if not svc.codegen.set_plugin_enabled(plugin_id, enabled):
            raise NotFoundError("Plugin not found")
        return 200, {"ok": True, "enabled": enabled}

    # ---- projects ----

    @router.route("GET", "/api/projects")
    def projects_list(req):
        return 200, {"projects": svc.projects.list()}

    @router.route("POST", "/api/projects")
    def projects_create(req):
        body = req.json()
        meta, clean = svc.projects.create(body.get("project") or body or {})
        return 201, {"ok": True, "meta": meta, "project": clean}

    @router.route("GET", "/api/projects/<project_id>")
    def projects_get(req):
        project_id, project = svc.projects.get(req.params["project_id"])
        return 200, {"id": project_id, "project": project}

    @router.route("PUT", "/api/projects/<project_id>")
    def projects_save(req):
        body = req.json()
        project = body.get("project") or body
        if body.get("name") and isinstance(project, dict) and not project.get("name"):
            project["name"] = body["name"]
        meta, clean = svc.projects.save(req.params["project_id"], project)
        return 200, {"ok": True, "meta": meta, "project": clean}

    @router.route("DELETE", "/api/projects/<project_id>")
    def projects_delete(req):
        svc.projects.delete(req.params["project_id"])
        return 200, {"ok": True}

    @router.route("POST", "/api/projects/<project_id>/duplicate")
    def projects_duplicate(req):
        meta, clean = svc.projects.duplicate(req.params["project_id"])
        return 201, {"ok": True, "meta": meta, "project": clean}

    @router.route("POST", "/api/projects/<project_id>/rename")
    def projects_rename(req):
        meta, clean = svc.projects.rename(req.params["project_id"], (req.json().get("name") or "").strip())
        return 200, {"ok": True, "meta": meta, "project": clean}

    # ---- code generation / build ----

    @router.route("POST", "/api/generate")
    def generate(req):
        result = svc.codegen.generate(req.json())
        return 200, {"code": result.code, "warnings": list(result.warnings)}

    @router.route("POST", "/api/compile")
    def compile_(req):
        result = svc.arduino.build(req.json())
        return (200 if result.ok else 400), result.as_dict()

    @router.route("POST", "/api/upload")
    def upload(req):
        project = req.json()
        port = str(project.get("port") or "").strip() if isinstance(project, dict) else ""
        if not port:
            return 400, {"ok": False, "stage": "upload", "code": "",
                         "log": "No serial port selected — pick the board's port (e.g. COM3)."}
        result = svc.arduino.build(project, port=port)
        return (200 if result.ok else 400), result.as_dict()

    # ---- terminal ----

    @router.route("POST", "/api/terminal")
    def terminal(req):
        from ..errors import ForbiddenError
        if req.headers.get("X-EmbedCo-Terminal") != "1":
            raise ForbiddenError("Terminal is only available from the local editor")
        return 200, svc.terminal.run(req.json().get("cmd", ""), client=req.client)

    return router
