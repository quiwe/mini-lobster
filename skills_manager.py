import json
from pathlib import Path

BASE_DIR = Path(__file__).parent
SKILLS_DIR = BASE_DIR / "skills"
SKILLS_REGISTRY = SKILLS_DIR / "registry.json"

SKILLS_DIR.mkdir(exist_ok=True)


def _registry() -> dict:
    if SKILLS_REGISTRY.exists():
        return json.loads(SKILLS_REGISTRY.read_text(encoding="utf-8"))
    return {"skills": []}


def _save_registry(reg: dict):
    SKILLS_REGISTRY.write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")


def list_skills() -> list[dict]:
    """列出所有已安装的 skill"""
    reg = _registry()
    return reg.get("skills", [])


def install_skill(name: str, content: str) -> str:
    """安装一个 skill（覆盖同名 skill）"""
    safe_name = "".join(c for c in name if c.isalnum() or c in "-_").strip()
    if not safe_name:
        return "Skill 名称无效，只允许字母、数字、-、_"

    skill_file = SKILLS_DIR / f"{safe_name}.md"
    skill_file.write_text(content.strip(), encoding="utf-8")

    reg = _registry()
    skills = reg.get("skills", [])
    # 移除同名 skill
    skills = [s for s in skills if s["name"] != safe_name]
    skills.append({"name": safe_name, "file": f"{safe_name}.md"})
    reg["skills"] = skills
    _save_registry(reg)

    return f"Skill '{safe_name}' 已安装，共 {len(skills)} 个技能"


def uninstall_skill(name: str) -> str:
    """卸载一个 skill"""
    safe_name = "".join(c for c in name if c.isalnum() or c in "-_").strip()
    skill_file = SKILLS_DIR / f"{safe_name}.md"
    if not skill_file.exists():
        return f"Skill 不存在: {safe_name}"

    skill_file.unlink()
    reg = _registry()
    reg["skills"] = [s for s in reg.get("skills", []) if s["name"] != safe_name]
    _save_registry(reg)
    return f"Skill '{safe_name}' 已卸载"


def load_all_skills() -> str:
    """加载所有已安装 skill 的完整内容"""
    reg = _registry()
    parts = []
    for skill in reg.get("skills", []):
        skill_file = SKILLS_DIR / skill["file"]
        if skill_file.exists():
            parts.append(f"=== Skill: {skill['name']} ===\n{skill_file.read_text(encoding='utf-8')}")
    return "\n\n".join(parts) if parts else ""
