"""Self-modification: settings gating, skill validation, and the code tier.

The code tier runs a real git flow against a throwaway repo with a fake
agent, so the isolation guarantees are tested rather than assumed.
"""

import subprocess
import sys
import textwrap
import time

import pytest

from app import db, selfmod, settings, skills

GOOD_SKILL = textwrap.dedent(
    """\
    ---
    name: car-service
    description: A car service record with the next service due.
    applies_to: [text, voice, image]
    extra_schema:
      garage:
        type: ["string", "null"]
        description: Who serviced it.
      next_service_due:
        type: ["string", "null"]
        description: ISO date of the next service.
    promote:
      due_at: next_service_due
      vendor: garage
    ---
    Focus on what was done and when the next one is due.
    """
)


def wait_for(job_id, timeout=15.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = db.get_job(job_id)
        if job["status"] not in ("running", "pending"):
            return job
        time.sleep(0.05)
    return db.get_job(job_id)


# --- settings gating --------------------------------------------------------


def test_self_modification_is_off_by_default():
    values = settings.get_all()
    assert values["self_modification_enabled"] is False
    assert values["self_modification_auto_code"] is False
    assert settings.should_auto_run("skill") is False
    assert settings.should_auto_run("code") is False


def test_a_request_is_saved_as_pending_when_disabled():
    job = selfmod.create_request(title="Later", prompt="Add a car servicing skill.", kind="skill")
    assert job["status"] == "pending"
    assert job["prompt"] == "Add a car servicing skill."


def test_code_stays_gated_even_once_self_modification_is_on():
    settings.set_many({"self_modification_enabled": True})
    assert settings.should_auto_run("skill") is True
    assert settings.should_auto_run("code") is False

    settings.set_many({"self_modification_auto_code": True})
    assert settings.should_auto_run("code") is True


def test_master_switch_overrides_both_tiers():
    settings.set_many({"self_modification_enabled": False, "self_modification_auto_code": True})
    assert settings.should_auto_run("code") is False
    assert settings.should_auto_run("skill") is False


def test_unknown_setting_is_rejected():
    with pytest.raises(ValueError, match="Unknown setting"):
        settings.set_many({"nonsense_key": 1})


def test_non_numeric_value_is_rejected():
    with pytest.raises(ValueError, match="expects a number"):
        settings.set_many({"agent_timeout_seconds": "soon"})


def test_empty_prompt_is_refused():
    with pytest.raises(ValueError, match="needs a prompt"):
        selfmod.create_request(title="x", prompt="   ", kind="skill")


def test_a_cancelled_job_cannot_be_claimed():
    job = selfmod.create_request(title="x", prompt="do a thing", kind="code")
    db.update_job(job["id"], status="cancelled")
    assert db.claim_job(job["id"]) is False


# --- skill tier: validation -------------------------------------------------


def test_a_well_formed_skill_is_accepted():
    name, skill = selfmod.validate_skill_file("car-service", GOOD_SKILL)
    assert name == "car-service"
    assert skill.promote["due_at"] == "next_service_due"


@pytest.mark.parametrize(
    "name,content,reason",
    [
        ("../../evil", GOOD_SKILL, "kebab-case"),
        ("Car Service", GOOD_SKILL, "kebab-case"),
        ("other-name", GOOD_SKILL, "does not match"),
        ("car-service", "just a plain file", "frontmatter"),
        ("task", GOOD_SKILL.replace("name: car-service", "name: task"), "already exists"),
        ("car-service", GOOD_SKILL.replace("due_at: next_service_due", "wat: next_service_due"), "not one of"),
        ("car-service", GOOD_SKILL.replace("due_at: next_service_due", "due_at: nope"), "isn't in extra_schema"),
        ("car-service", GOOD_SKILL.replace("[text, voice, image]", "[telepathy]"), "Unknown applies_to"),
    ],
)
def test_malformed_skills_are_refused(name, content, reason):
    with pytest.raises(ValueError, match=reason):
        selfmod.validate_skill_file(name, content)


def test_yaml_below_the_frontmatter_is_refused():
    """It parses as prose and is silently ignored -- an authored file once put
    `promote:` there and quietly lost its agenda integration."""
    stray = GOOD_SKILL.replace("promote:\n  due_at: next_service_due\n  vendor: garage\n", "")
    stray += "\npromote:\n  due_at: next_service_due\n"
    with pytest.raises(ValueError, match="must be inside the single --- frontmatter"):
        selfmod.validate_skill_file("car-service", stray)


# --- skill tier: end to end -------------------------------------------------


@pytest.fixture
def temp_skills(tmp_path, monkeypatch):
    from app import config

    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "general.md").write_text(
        "---\nname: general\ndescription: Fallback.\nextra_schema: {}\n---\nGeneral.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(selfmod, "SKILLS_DIR", skills_dir)
    monkeypatch.setattr(skills, "SKILLS_DIR", skills_dir)
    monkeypatch.setattr(config, "SKILLS_DIR", skills_dir)
    return skills_dir


def test_an_authored_skill_is_written_and_loads(temp_skills, stub_llm):
    stub_llm.returns({"name": "car-service", "file_content": GOOD_SKILL, "reasoning": "Nothing tracks servicing."})
    settings.set_many({"self_modification_enabled": True})

    job = wait_for(selfmod.create_request(title="Track servicing", prompt="Track my car servicing.", kind="skill")["id"])

    assert job["status"] == "succeeded", job["error"]
    assert (temp_skills / "car-service.md").exists()
    assert skills.get_skill("car-service") is not None
    assert "due_at <- next_service_due" in job["result"]


def test_the_same_skill_is_not_written_twice(temp_skills, stub_llm):
    stub_llm.returns(
        {"name": "car-service", "file_content": GOOD_SKILL, "reasoning": "x"},
        {"name": "car-service", "file_content": GOOD_SKILL, "reasoning": "x"},
    )
    settings.set_many({"self_modification_enabled": True})

    wait_for(selfmod.create_request(title="a", prompt="p", kind="skill")["id"])
    second = wait_for(selfmod.create_request(title="b", prompt="p", kind="skill")["id"])

    assert second["status"] == "failed"
    assert "already exists" in second["error"]


# --- code tier --------------------------------------------------------------


@pytest.fixture
def fake_repo(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("print('v1')\n", encoding="utf-8")
    for args in (
        ["init", "-q"], ["config", "user.email", "t@t.t"], ["config", "user.name", "T"],
        ["add", "-A"], ["commit", "-qm", "init"],
    ):
        subprocess.run(["git", *args], cwd=repo, capture_output=True)

    agent = tmp_path / "fake_agent.py"
    agent.write_text(
        "import sys, pathlib\n"
        "prompt = sys.argv[sys.argv.index('-p') + 1]\n"
        "pathlib.Path('app.py').write_text(\"print('v2')  # \" + prompt + \"\\n\")\n"
        "print('agent done')\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(selfmod, "BASE_DIR", repo)
    settings.set_many({
        "self_modification_enabled": True,
        "self_modification_auto_code": True,
        "agent_command": f'"{sys.executable}" "{agent}"',
    })
    return repo


def git_out(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True).stdout.strip()


def test_changes_land_on_a_branch_and_are_never_merged(fake_repo):
    job = wait_for(selfmod.create_request(title="Bump version", prompt="Change to v2", kind="code")["id"], timeout=40)

    assert job["status"] == "succeeded", job["error"]
    assert job["branch"].startswith("selfmod/")
    # Back on the original branch, with the working copy untouched.
    assert git_out(fake_repo, "rev-parse", "--abbrev-ref", "HEAD") in ("master", "main")
    assert (fake_repo / "app.py").read_text().strip() == "print('v1')"
    # The work exists, but only on its own branch.
    assert "v2" in git_out(fake_repo, "show", f"{job['branch']}:app.py")


def test_a_dirty_tree_blocks_the_job(fake_repo):
    (fake_repo / "untracked.txt").write_text("my work\n", encoding="utf-8")

    assert any("uncommitted" in p for p in selfmod.preflight_code())
    job = wait_for(selfmod.create_request(title="Refuse", prompt="do it", kind="code")["id"])
    assert job["status"] == "failed"
    assert "uncommitted" in job["error"]


def test_a_missing_agent_reports_clearly_and_restores_the_branch(fake_repo):
    settings.set_many({"agent_command": "definitely-not-a-real-binary-xyz"})
    job = wait_for(selfmod.create_request(title="Missing", prompt="x", kind="code")["id"])

    assert job["status"] == "failed"
    assert "not found" in job["error"]
    assert git_out(fake_repo, "rev-parse", "--abbrev-ref", "HEAD") in ("master", "main")


def test_a_manual_run_overrides_the_settings(fake_repo):
    settings.set_many({"self_modification_enabled": False})
    job = selfmod.create_request(title="Later", prompt="Change to v2", kind="code")
    assert job["status"] == "pending"

    selfmod.start_job(job["id"])
    assert wait_for(job["id"], timeout=40)["status"] == "succeeded"
