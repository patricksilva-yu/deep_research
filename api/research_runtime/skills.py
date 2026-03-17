import os
from pathlib import Path
from typing import Dict, List, Optional


PROJECT_SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"
WORKSPACE_AGENTS_SKILLS_DIR = Path(__file__).resolve().parents[2] / ".agents" / "skills"
CODEX_SKILLS_DIR = Path(os.getenv("CODEX_HOME", Path.home() / ".codex")) / "skills"
AGENTS_SKILLS_DIR = Path.home() / ".agents" / "skills"


def _parse_skill_metadata(text: str) -> Dict[str, str]:
    metadata: Dict[str, str] = {}
    if not text.startswith("---"):
        return metadata

    lines = text.splitlines()
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip()
    return metadata


def _load_skill_text(skill_dir: Path) -> Optional[str]:
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.exists():
        return None
    try:
        return skill_file.read_text(encoding="utf-8")
    except OSError:
        return None


def list_project_skills() -> List[dict]:
    skills_by_name: Dict[str, dict] = {}
    for skills_dir in [PROJECT_SKILLS_DIR, WORKSPACE_AGENTS_SKILLS_DIR, CODEX_SKILLS_DIR, AGENTS_SKILLS_DIR]:
        if not skills_dir.exists():
            continue

        for skill_dir in sorted(skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue

            text = _load_skill_text(skill_dir)
            if text is None:
                continue
            metadata = _parse_skill_metadata(text)
            skills_by_name[skill_dir.name] = {
                "name": skill_dir.name,
                "path": str(skill_dir / "SKILL.md"),
                "description": metadata.get("description", ""),
            }
    return list(skills_by_name.values())


def load_project_skill(skill_name: str) -> str:
    for skills_dir in [PROJECT_SKILLS_DIR, WORKSPACE_AGENTS_SKILLS_DIR, CODEX_SKILLS_DIR, AGENTS_SKILLS_DIR]:
        skill_file = skills_dir / skill_name / "SKILL.md"
        if skill_file.exists():
            return skill_file.read_text(encoding="utf-8")
    raise FileNotFoundError(f"Skill '{skill_name}' not found.")
