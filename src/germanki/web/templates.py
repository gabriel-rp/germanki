from pathlib import Path
from typing import Final
from fastapi.templating import Jinja2Templates


def get_basename(p: str) -> str:
    return Path(p).name if p else ""


def get_noun_color(extra: str | None) -> str | None:
    if not extra:
        return None
    first_word = extra.strip().split()[0].lower()
    if first_word == "der":
        return "blue"
    elif first_word == "die":
        return "red"
    elif first_word == "das":
        return "black"
    return None


TEMPLATE_FILTERS = {
    "noun_color": get_noun_color,
    "basename": get_basename,
}


def get_templates(base_dir: Path) -> Jinja2Templates:
    TEMPLATES_DIR: Final[Path] = base_dir / "templates"
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    for filter_name, filter in TEMPLATE_FILTERS.items():
        templates.env.filters[filter_name] = filter
    return templates
