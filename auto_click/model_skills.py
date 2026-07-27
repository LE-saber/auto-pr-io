"""Small local skill library for automation models."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class ModelSkill:
    name: str
    filename: str
    content: str


class ModelSkillLibrary:
    """Load markdown skills and select the most relevant notes for a task."""

    def __init__(self, skills_dir: str | Path | None = None):
        base_dir = Path(__file__).resolve().parents[1]
        self.skills_dir = Path(skills_dir) if skills_dir else base_dir / "skills"

    def relevant_context(self, query: str, max_skills: int = 3, max_chars: int = 3000) -> str:
        skills = self._load()
        if not skills:
            return ""

        forced_names = self._forced_skill_names()
        forced = [skill for skill in skills if self._matches_forced(skill, forced_names)]
        scored = [(self._score(skill, query), idx, skill) for idx, skill in enumerate(skills)]
        scored.sort(key=lambda item: (-item[0], item[1]))
        selected = forced[:max_skills]
        selected_names = {skill.name for skill in selected}
        selected_paths = {self._filename_for(skill) for skill in selected}
        for score, _, skill in scored:
            if score <= 0 or len(selected) >= max_skills:
                continue
            if skill.name in selected_names or self._filename_for(skill) in selected_paths:
                continue
            selected.append(skill)
            selected_names.add(skill.name)
            selected_paths.add(self._filename_for(skill))
        if not selected:
            return ""

        parts: list[str] = []
        used = 0
        for skill in selected:
            remaining = max_chars - used
            if remaining <= 0:
                break
            body = skill.content.strip()
            if len(body) > remaining:
                body = body[:remaining].rstrip() + "\n..."
            parts.append(f"Skill: {skill.name}\n{body}")
            used += len(body)
        return "\n\n".join(parts)

    def _load(self) -> list[ModelSkill]:
        if not self.skills_dir.exists():
            return []
        skills: list[ModelSkill] = []
        for path in sorted(self.skills_dir.glob("*.md")):
            try:
                content = path.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if not content:
                continue
            name = self._title(path, content)
            skills.append(ModelSkill(name=name, filename=path.name, content=content))
        return skills

    @staticmethod
    def _forced_skill_names() -> set[str]:
        try:
            from settings_store import get_skill_settings
        except Exception:
            return set()
        forced = get_skill_settings().get("forced", [])
        if not isinstance(forced, list):
            return set()
        return {str(name).strip().lower() for name in forced if str(name).strip()}

    @staticmethod
    def _matches_forced(skill: ModelSkill, forced_names: Iterable[str]) -> bool:
        names = set(forced_names)
        return skill.name.lower() in names or ModelSkillLibrary._filename_for(skill).lower() in names

    @staticmethod
    def _filename_for(skill: ModelSkill) -> str:
        return skill.filename

    @staticmethod
    def _title(path: Path, content: str) -> str:
        first = content.splitlines()[0].strip()
        if first.startswith("#"):
            return first.lstrip("#").strip() or path.stem
        return path.stem

    @staticmethod
    def _score(skill: ModelSkill, query: str) -> int:
        haystack = f"{skill.name}\n{skill.content}".lower()
        tokens = set(re.findall(r"[a-zA-Z0-9_.:/+-]{2,}|[\u4e00-\u9fff]{2,}", query.lower()))
        return sum(1 for token in tokens if token in haystack)
