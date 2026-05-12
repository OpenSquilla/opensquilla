"""Loader namespace fallback + ClawHub field-alias contract tests."""

from __future__ import annotations

from pathlib import Path

from opensquilla.skills.loader import SkillLoader

ROOT = Path(__file__).resolve().parents[1]
BUNDLED = ROOT / "src" / "opensquilla" / "skills" / "bundled"


def _write_skill(dir_path: Path, name: str, body: str) -> None:
    skill_dir = dir_path / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(body, encoding="utf-8")


def test_clawdbot_namespace_resolves(tmp_path: Path) -> None:
    """`metadata.clawdbot.requires.bins` must populate SkillSpec.metadata.requires.bins."""
    _write_skill(
        tmp_path,
        "clawdbot-skill",
        """---
name: clawdbot-skill
description: Synthetic skill exercising the clawdbot namespace fallback.
metadata:
  clawdbot:
    requires:
      bins: [foo]
---

# body
""",
    )
    loader = SkillLoader(bundled_dir=tmp_path)
    spec = loader.get_by_name("clawdbot-skill")
    assert spec is not None
    assert spec.metadata is not None
    assert spec.metadata.requires is not None
    assert spec.metadata.requires.bins == ["foo"]


def test_commands_alias_for_bins(tmp_path: Path) -> None:
    """`requires.commands` should map onto `requires.bins` when bins is absent."""
    _write_skill(
        tmp_path,
        "commands-alias",
        """---
name: commands-alias
description: Synthetic skill exercising the requires.commands alias.
metadata:
  platform:
    requires:
      commands: [bar]
---

# body
""",
    )
    loader = SkillLoader(bundled_dir=tmp_path)
    spec = loader.get_by_name("commands-alias")
    assert spec is not None
    assert spec.metadata is not None
    assert spec.metadata.requires is not None
    assert spec.metadata.requires.bins == ["bar"]


def test_explicit_bins_wins_over_commands(tmp_path: Path) -> None:
    """When both `bins` and `commands` are present, `bins` is authoritative."""
    _write_skill(
        tmp_path,
        "bins-wins",
        """---
name: bins-wins
description: bins wins over commands when both present.
metadata:
  platform:
    requires:
      bins: [keep]
      commands: [drop]
---

# body
""",
    )
    loader = SkillLoader(bundled_dir=tmp_path)
    spec = loader.get_by_name("bins-wins")
    assert spec is not None
    assert spec.metadata is not None
    assert spec.metadata.requires is not None
    assert spec.metadata.requires.bins == ["keep"]


def test_bom_and_crlf_skill_frontmatter_parse(tmp_path: Path) -> None:
    skill_dir = tmp_path / "bom-crlf"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\r\nname: bom-crlf\r\ndescription: Handles Windows-authored skills.\r\n---\r\nBody\r\n",
        encoding="utf-8-sig",
    )

    loader = SkillLoader(bundled_dir=tmp_path)
    spec = loader.get_by_name("bom-crlf")

    assert spec is not None
    assert spec.description == "Handles Windows-authored skills."


def test_existing_bundled_skills_still_parse() -> None:
    """Regression guard: every bundled SKILL.md must still parse after the patch."""
    loader = SkillLoader(bundled_dir=BUNDLED)
    skills = loader.load_all()
    parsed_names = {spec.name for spec in skills}

    on_disk = {
        path.name
        for path in BUNDLED.iterdir()
        if path.is_dir() and (path / "SKILL.md").is_file()
    }
    assert on_disk.issubset(parsed_names), (
        f"loader dropped bundled skill(s): {on_disk - parsed_names}"
    )
