from pathlib import Path

import pytest

from html_mcp_web import config as config_module
from html_mcp_web.config import Config, create_config, find_config, get_main_file, get_template_dir, load_config


def test_missing_config_explains_project_setup(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError, match="html-mcp-web init --layout slides"):
        load_config()


def artifact(layout: str = "slides", main: str = "artifact.html", **values) -> dict:
    return {"label": layout.title(), "layout": layout, "main": main, **values}


def test_create_and_find_config_from_child(tmp_path: Path) -> None:
    main = tmp_path / "artifact.html"
    main.write_text("<p>artifact</p>", encoding="utf-8")
    config_path = create_config(layout="slides", main="artifact.html", port=9001,
                                output_path=tmp_path / ".html-mcp-web.yaml")
    child = tmp_path / "nested"
    child.mkdir()

    assert find_config(child) == config_path
    config = load_config(config_path)
    assert list(config.artifacts) == ["slides"]
    assert config.artifacts["slides"].layout == "slides"
    assert config.artifacts["slides"].main == "artifact.html"
    assert config.port == 9001
    assert get_main_file(config, "slides") == main


def test_create_refuses_to_overwrite(tmp_path: Path) -> None:
    target = tmp_path / ".html-mcp-web.yaml"
    target.write_text("artifacts: {}\n", encoding="utf-8")
    with pytest.raises(FileExistsError):
        create_config(layout="report", output_path=target)


def test_config_requires_artifacts() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        Config.from_dict({"port": 8765})


def test_config_rejects_non_html_main() -> None:
    with pytest.raises(ValueError, match="HTML"):
        Config.from_dict({"artifacts": {"report": artifact("report", "report.md")}})


def test_config_requires_supported_layout() -> None:
    with pytest.raises(ValueError, match="requires layout"):
        Config.from_dict({"artifacts": {"brief": {"label": "Brief", "main": "brief.html"}}})
    with pytest.raises(ValueError, match="slides or report"):
        Config.from_dict({"artifacts": {"brief": artifact("book")}})


def test_template_requires_content() -> None:
    with pytest.raises(ValueError, match="together"):
        Config.from_dict({"artifacts": {"slides": artifact(template="neutral-slides")}})


def test_template_content_must_differ_from_main() -> None:
    with pytest.raises(ValueError, match="differ"):
        Config.from_dict({"artifacts": {"slides": artifact(main="slides.html", template="neutral-slides", content="slides.html")}})


def test_multiple_artifacts_round_trip() -> None:
    config = Config.from_dict({"artifacts": {
        "slides": artifact(main="slides.html", template="neutral-slides", content="slides-content.html"),
        "report": artifact("report", "report.html", template="neutral-report", content="report-content.html"),
    }})
    data = config.to_dict()
    assert list(data["artifacts"]) == ["slides", "report"]
    assert Config.from_dict(data).artifacts["report"].template == "neutral-report"


def test_unknown_keys_fail() -> None:
    with pytest.raises(ValueError, match="unknown configuration keys"):
        Config.from_dict({"artifacts": {"slides": artifact()}, "main": "old.html"})
    with pytest.raises(ValueError, match="unknown keys"):
        Config.from_dict({"artifacts": {"slides": artifact(extra=True)}})


def test_artifact_main_files_are_unique() -> None:
    with pytest.raises(ValueError, match="unique"):
        Config.from_dict({"artifacts": {
            "first": artifact(main="same.html"),
            "second": artifact("report", main="same.html"),
        }})


def test_template_name_is_validated() -> None:
    with pytest.raises(ValueError, match="directory name"):
        Config.from_dict({"artifacts": {"slides": artifact(template="../evil", content="content.html")}})


def test_user_template_takes_priority_over_public_template(tmp_path: Path, monkeypatch) -> None:
    user_config = tmp_path / ".config" / "html-mcp-web"
    user_template = user_config / "templates" / "neutral-slides"
    user_template.mkdir(parents=True)
    monkeypatch.setattr(config_module, "USER_CONFIG_DIR", user_config)
    config = Config.from_dict({"artifacts": {
        "slides": artifact(template="neutral-slides", content="content.html"),
    }})

    assert get_template_dir(config, "slides") == user_template


def test_public_template_is_used_when_user_template_is_absent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(config_module, "USER_CONFIG_DIR", tmp_path / ".config" / "html-mcp-web")
    config = Config.from_dict({"artifacts": {
        "slides": artifact(template="neutral-slides", content="content.html"),
    }})

    template = get_template_dir(config, "slides")
    assert template is not None
    assert template.name == "neutral-slides"
    assert template.parent.name == "templates"
    assert template.is_dir()
