#!/usr/bin/env python3
"""Assemble the Hugging Face Space folder for Lola-Bla from this repository.

    python3 publish/build_space.py [--out DIR] [--pollen DIR]

The Space holds one installable package: our app, the family console, Lola's profile and tools,
and a modified copy of Pollen Robotics' conversation app (their code at the pinned commit plus
our patch). Nothing private is read: no database, no keys, no tokens.
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
POLLEN_URL = "https://github.com/pollen-robotics/reachy_mini_conversation_app.git"
SKIP_TOOLS = {"test_mic_handoff.py"}  # a diagnostic, not part of the shipped app
OUR_OWN = {"reachy-mini-conversation-app", "lola-console"}  # bundled, so never a dependency
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "tests", ".env", "*.json")
SECRETS = re.compile(r"hf_[A-Za-z0-9]{20,}|\+\d{8,}|BEGIN [A-Z ]*PRIVATE KEY")
FORBIDDEN = ("*.db", "*.pem", "hf_token", ".env", "*.wav")

README = """---
title: Lola-Bla
emoji: 💛
colorFrom: yellow
colorTo: purple
sdk: static
pinned: false
short_description: Family voice messages for the Reachy Mini
tags:
 - reachy_mini
 - reachy_mini_python_app
---

# Lola-Bla

**talk to abuelo without a phone.** Lola-Bla lets a young child hear and answer Signal voice messages from family far away, using a Reachy Mini Wireless. Only people you approve, one by one, can reach her.

## What you need

- A Reachy Mini Wireless
- A Signal account for the robot, linked from the app's settings page
- Docker on the robot, for the Signal connection

## Privacy in short

The audio of messages, the contacts and the Signal keys stay on the robot. While the app runs, the live conversation is handled by Pollen's hosted voice service. A short task text may go to Hugging Face's inference service to understand a request; without it, simple rules on the robot take over.

## Based on Pollen's app

This package includes a modified copy of the [Reachy Mini conversation app](https://github.com/pollen-robotics/reachy_mini_conversation_app) by Pollen Robotics (Apache-2.0). If you have that app installed, uninstall it before installing Lola-Bla. See NOTICE for what was changed.

License: Apache-2.0.
"""

INDEX = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Lola-Bla</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
<main>
<img src="lola-bla-mark.svg" alt="Lola-Bla" width="160" height="160">
<h1>Lola-Bla</h1>
<p class="tag">talk to abuelo without a phone.</p>
<p>Family voice messages for the Reachy Mini. Lola hears Signal voice messages from the people you approve and answers them with her own voice.</p>
<p class="small">Needs a Reachy Mini Wireless and a Signal account for the robot. Install it from the app list in Reachy Mini Control.</p>
</main>
</body>
</html>
"""

STYLE = """:root { --banana: #F7D33E; --lila: #C9B3F2; --violeta: #7B4FC4; --berenjena: #2A1640; --crema: #FFF8E7; }
* { box-sizing: border-box; }
body { margin: 0; background: var(--banana); color: var(--berenjena); font-family: Georgia, serif; line-height: 1.5; }
main { max-width: 34rem; margin: 0 auto; padding: 3rem 1rem; text-align: center; }
h1 { font-size: 2.6rem; margin: 0.5rem 0 0; }
.tag { color: var(--violeta); font-style: italic; font-size: 1.2rem; margin-top: 0.2rem; }
.small { font-size: 0.95rem; background: var(--crema); border: 3px solid var(--berenjena); border-radius: 18px; padding: 0.8rem 1rem; }
"""


def run(cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True).stdout


def req_name(req):
    return re.split(r"[<>=!~;\s\[]", req.strip(), maxsplit=1)[0].lower().replace("_", "-")


def merged_dependencies(pollen_tree):
    deps = {}
    pollen = tomllib.loads((pollen_tree / "pyproject.toml").read_text(encoding="utf-8"))["project"]["dependencies"]
    ours = []
    for f in (REPO / "console" / "pyproject.toml", REPO / "app" / "pyproject.toml"):
        ours += tomllib.loads(f.read_text(encoding="utf-8"))["project"]["dependencies"]
    for req in pollen + ours:
        if req_name(req) not in OUR_OWN:
            deps[req_name(req)] = req.strip()
    return [deps[k] for k in sorted(deps)]


def pyproject_text(pollen_tree):
    version = tomllib.loads((REPO / "app" / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    deps = ",\n    ".join(json.dumps(d) for d in merged_dependencies(pollen_tree))
    return f"""[build-system]
requires = ["setuptools>=64"]
build-backend = "setuptools.build_meta"

[project]
name = "lola_bla"
version = "{version}"
description = "Lola-Bla: family voice messages for the Reachy Mini"
readme = "README.md"
license = {{ text = "Apache-2.0" }}
requires-python = ">=3.11"
keywords = ["reachy-mini-app"]
dependencies = [
    {deps},
]

[project.entry-points."reachy_mini_apps"]
lola_bla = "lola_bla.main:LolaBla"

[tool.setuptools]
package-dir = {{ "" = "src" }}
include-package-data = true

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
lola_bla = ["content/**/*"]
lola_console = ["templates/*", "static/*", "static/fonts/*"]
reachy_mini_conversation_app = ["static/**/*", ".env.example"]
reachy_talk_data = ["profiles/**/*.md"]
"""


def notice_text(commit):
    return f"""Lola-Bla
Copyright 2026 Betiana Felice. Licensed under the Apache License 2.0 (see LICENSE).

This package includes a modified copy of the Reachy Mini conversation app
by Pollen Robotics, licensed under the Apache License 2.0 (see LICENSE-Pollen).
Original: {POLLEN_URL}
Commit: {commit}
Change: a two-line patch that gives tools access to the live microphone stream
(it lets a tool mute and unmute the microphone). Nothing else was changed.
"""


def clear(out):
    """Empty the output folder but keep a .git folder (a later publish needs its link to the Space)."""
    if out.exists() and any(out.iterdir()):
        readme = out / "README.md"
        if not (readme.is_file() and "title: Lola-Bla" in readme.read_text(encoding="utf-8")):
            raise SystemExit(f"{out} exists and does not look like a Lola-Bla Space. Nothing changed.")
        for child in out.iterdir():
            if child.name == ".git":
                continue
            shutil.rmtree(child) if child.is_dir() else child.unlink()
    out.mkdir(parents=True, exist_ok=True)


def check(out):
    problems = []
    for f in sorted(out.rglob("*")):
        rel = f.relative_to(out)
        if ".git" in rel.parts or not f.is_file():
            continue
        if any(f.match(pat) for pat in FORBIDDEN):
            problems.append(f"forbidden file: {rel}")
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if SECRETS.search(text):
            problems.append(f"looks like a secret or a number: {rel}")
        if f.suffix == ".py":
            try:
                compile(text, str(f), "exec")
            except SyntaxError as e:
                problems.append(f"does not compile: {rel}: {e}")
    if problems:
        raise SystemExit("STOP, not a clean build:\n  " + "\n  ".join(problems))


def build(pollen_tree, out, commit="unknown"):
    """pollen_tree: a plain folder with Pollen's app (already patched). out: where the Space goes."""
    pollen_tree, out = Path(pollen_tree), Path(out)
    clear(out)
    src = out / "src"
    shutil.copytree(REPO / "app" / "src" / "lola_bla", src / "lola_bla", ignore=IGNORE)
    shutil.copytree(REPO / "console" / "lola_console", src / "lola_console", ignore=IGNORE)
    shutil.copytree(pollen_tree / "src" / "reachy_mini_conversation_app", src / "reachy_mini_conversation_app", ignore=IGNORE)
    data = src / "reachy_talk_data"
    (data / "profiles").mkdir(parents=True)
    (data / "__init__.py").write_text("", encoding="utf-8")
    for profile in sorted((pollen_tree / "profiles").glob("*/profile.md")):
        (data / "profiles" / profile.parent.name).mkdir()
        shutil.copy2(profile, data / "profiles" / profile.parent.name / "profile.md")
    content = src / "lola_bla" / "content"
    (content / "profiles" / "lola").mkdir(parents=True)
    (content / "tools").mkdir()
    (content / "messaging").mkdir()
    profile = (REPO / "profiles" / "lola" / "profile.md").read_text(encoding="utf-8")
    profile = "".join(line for line in profile.splitlines(keepends=True) if "test_mic_handoff" not in line)
    (content / "profiles" / "lola" / "profile.md").write_text(profile, encoding="utf-8")
    for tool in sorted((REPO / "app" / "tools").glob("*.py")):
        if tool.name not in SKIP_TOOLS:
            shutil.copy2(tool, content / "tools" / tool.name)
    for f in sorted((REPO / "app" / "local_data").iterdir()):
        if f.suffix in (".py", ".sql"):
            shutil.copy2(f, content / "messaging" / f.name)
    (out / "pyproject.toml").write_text(pyproject_text(pollen_tree), encoding="utf-8")
    (out / "README.md").write_text(README, encoding="utf-8")
    (out / "index.html").write_text(INDEX, encoding="utf-8")
    (out / "style.css").write_text(STYLE, encoding="utf-8")
    (out / "NOTICE").write_text(notice_text(commit), encoding="utf-8")
    shutil.copy2(REPO / "LICENSE", out / "LICENSE")
    if (pollen_tree / "LICENSE").is_file():
        shutil.copy2(pollen_tree / "LICENSE", out / "LICENSE-Pollen")
    shutil.copy2(REPO / "docs" / "brand" / "lola-bla-mark.svg", out / "lola-bla-mark.svg")
    check(out)
    return out


def prepare_pollen(given, work):
    """A plain, patched copy of Pollen's app at the pinned commit. Returns (folder, commit)."""
    commit = (REPO / "app" / "patches" / "POLLEN_COMMIT").read_text(encoding="utf-8").strip()
    if given:
        clone = Path(given)
    else:
        clone = work / "clone"
        run(["git", "clone", "--quiet", POLLEN_URL, str(clone)])
        run(["git", "-C", str(clone), "checkout", "--quiet", commit])
    head = run(["git", "-C", str(clone), "rev-parse", "HEAD"]).strip()
    if head != commit:
        raise SystemExit(f"{clone} is at {head[:9]}, the pinned commit is {commit[:9]}. Nothing changed.")
    tree = work / "tree"
    tree.mkdir()
    archive = subprocess.run(["git", "-C", str(clone), "archive", "--format=tar", "HEAD"], check=True, capture_output=True).stdout
    subprocess.run(["tar", "-x", "-C", str(tree)], input=archive, check=True)
    run(["git", "apply", str(REPO / "app" / "patches" / "pollen-conversation-app.patch")], cwd=tree)
    return tree, commit


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", default=str(Path.home() / "lola-bla-space"), help="where the Space folder goes")
    parser.add_argument("--pollen", help="an existing clone of Pollen's app, checked out at the pinned commit")
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory() as tmp:
        tree, commit = prepare_pollen(args.pollen, Path(tmp))
        out = build(tree, args.out, commit)
    files = sum(1 for f in out.rglob("*") if f.is_file() and ".git" not in f.relative_to(out).parts)
    print(f"Space folder ready: {out} ({files} files, Pollen's app at {commit[:9]} plus our patch)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
