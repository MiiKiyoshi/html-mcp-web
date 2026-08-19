"""Project configuration for html-mcp-web."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml


DEFAULT_CONFIG_NAME = ".html-mcp-web.yaml"
DEFAULT_PORT = 8765
DEFAULT_WATCH = ["*.html", "*.css", "*.js", "*.svg", "*.png", "*.jpg", "*.jpeg", "*.gif", "*.webp"]
USER_CONFIG_DIR = Path.home() / ".config" / "html-mcp-web"
LayoutMode = Literal["slides", "report"]
LAYOUT_MODES = {"slides", "report"}


@dataclass(frozen=True)
class ArtifactConfig:
    label: str
    layout: LayoutMode
    main: str
    template: str | None = None
    content: str | None = None

    @classmethod
    def from_dict(cls, artifact_id: str, data: dict[str, Any]) -> "ArtifactConfig":
        unknown = set(data) - {"label", "layout", "main", "template", "content"}
        if unknown:
            raise ValueError(f"artifact {artifact_id!r} has unknown keys: {', '.join(sorted(unknown))}")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", artifact_id):
            raise ValueError(f"artifact id must contain only letters, numbers, underscores, and hyphens: {artifact_id!r}")
        if "layout" not in data:
            raise ValueError(f"artifact {artifact_id!r} requires layout")
        if "main" not in data:
            raise ValueError(f"artifact {artifact_id!r} requires main")
        layout = str(data["layout"])
        main = str(data["main"])
        label = str(data["label"]) if "label" in data else artifact_id
        template = str(data["template"]) if "template" in data and data["template"] else None
        content = str(data["content"]) if "content" in data and data["content"] else None
        if layout not in LAYOUT_MODES:
            raise ValueError(f"artifact {artifact_id!r} layout must be slides or report")
        if not label.strip():
            raise ValueError(f"artifact {artifact_id!r} label must not be empty")
        if not main.endswith((".html", ".htm")):
            raise ValueError(f"artifact {artifact_id!r} main must name an HTML file")
        if (template is None) != (content is None):
            raise ValueError(f"artifact {artifact_id!r} template and content must be set together")
        if template is not None and not re.fullmatch(r"[A-Za-z0-9_-]+", template):
            raise ValueError(f"artifact {artifact_id!r} template must be a directory name under templates/")
        if content is not None:
            if not content.endswith((".html", ".htm")):
                raise ValueError(f"artifact {artifact_id!r} content must name an HTML file")
            if content == main:
                raise ValueError(f"artifact {artifact_id!r} content and main must differ")
        return cls(label=label.strip(), layout=layout, main=main, template=template, content=content)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"label": self.label, "layout": self.layout, "main": self.main}
        if self.template is not None:
            data["template"] = self.template
            data["content"] = self.content
        return data


@dataclass
class Config:
    artifacts: dict[str, ArtifactConfig]
    watch: list[str] = field(default_factory=lambda: list(DEFAULT_WATCH))
    ignore: list[str] = field(default_factory=list)
    port: int = DEFAULT_PORT
    config_path: Path | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any], config_path: Path | None = None) -> "Config":
        unknown = set(data) - {"artifacts", "watch", "ignore", "port"}
        if unknown:
            raise ValueError(f"unknown configuration keys: {', '.join(sorted(unknown))}")
        if "artifacts" not in data or not isinstance(data["artifacts"], dict) or not data["artifacts"]:
            raise ValueError("artifacts must be a non-empty mapping")
        artifacts = {
            str(artifact_id): ArtifactConfig.from_dict(str(artifact_id), value)
            for artifact_id, value in data["artifacts"].items()
            if isinstance(value, dict)
        }
        if len(artifacts) != len(data["artifacts"]):
            raise ValueError("each artifact must be a mapping")
        main_files = [artifact.main for artifact in artifacts.values()]
        if len(set(main_files)) != len(main_files):
            raise ValueError("artifact main files must be unique")
        watch = [str(value) for value in data["watch"]] if "watch" in data else list(DEFAULT_WATCH)
        ignore = [str(value) for value in data["ignore"]] if "ignore" in data else []
        port = int(data["port"]) if "port" in data else DEFAULT_PORT
        if not 1 <= port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        return cls(artifacts=artifacts, watch=watch, ignore=ignore, port=port, config_path=config_path)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifacts": {artifact_id: artifact.to_dict() for artifact_id, artifact in self.artifacts.items()},
            "watch": list(self.watch),
            "ignore": list(self.ignore),
            "port": self.port,
        }


def find_config(start_dir: Path | None = None) -> Path | None:
    current = (start_dir if start_dir is not None else Path.cwd()).resolve()
    while True:
        candidate = current / DEFAULT_CONFIG_NAME
        if candidate.exists():
            return candidate
        if current == current.parent:
            return None
        current = current.parent


def load_config(path: Path | None = None) -> Config:
    config_path = path if path is not None else find_config()
    if config_path is None:
        raise FileNotFoundError(
            f"{DEFAULT_CONFIG_NAME} was not found. In the project directory, run: "
            "html-mcp-web init --layout slides --main artifact.html --port 8765 "
            "(use report for A4 and replace the file and port with the requested values)"
        )
    loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{config_path} must contain a YAML mapping")
    return Config.from_dict(loaded, config_path=config_path.resolve())


def create_config(
    layout: LayoutMode,
    main: str = "artifact.html",
    watch: list[str] | None = None,
    ignore: list[str] | None = None,
    port: int = DEFAULT_PORT,
    output_path: Path | None = None,
    template: str | None = None,
    content: str | None = None,
) -> Path:
    target = output_path if output_path is not None else Path.cwd() / DEFAULT_CONFIG_NAME
    if target.exists():
        raise FileExistsError(f"{target} already exists")
    artifact_id = layout
    artifact: dict[str, Any] = {"label": layout.title(), "layout": layout, "main": main}
    if template is not None or content is not None:
        artifact["template"] = template
        artifact["content"] = content
    config = Config.from_dict(
        {
            "artifacts": {artifact_id: artifact},
            "watch": list(watch) if watch is not None else list(DEFAULT_WATCH),
            "ignore": list(ignore) if ignore is not None else [],
            "port": port,
        },
        config_path=target,
    )
    target.write_text(yaml.safe_dump(config.to_dict(), sort_keys=False), encoding="utf-8")
    return target


def write_config(config: Config) -> None:
    if config.config_path is None:
        raise ValueError("configuration has no file path")
    config.config_path.write_text(yaml.safe_dump(config.to_dict(), sort_keys=False), encoding="utf-8")


def get_project_dir(config: Config) -> Path:
    if config.config_path is None:
        raise ValueError("configuration has no file path")
    return config.config_path.parent


def get_main_file(config: Config, artifact_id: str) -> Path:
    return get_project_dir(config) / config.artifacts[artifact_id].main


def get_content_file(config: Config, artifact_id: str) -> Path | None:
    content = config.artifacts[artifact_id].content
    return None if content is None else get_project_dir(config) / content


def get_template_dir(config: Config, artifact_id: str) -> Path | None:
    template = config.artifacts[artifact_id].template
    if template is None:
        return None
    user_template = USER_CONFIG_DIR / "templates" / template
    if user_template.is_dir():
        return user_template
    return Path(__file__).resolve().parent.parent / "templates" / template
