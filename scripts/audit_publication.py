"""Read-only staged/history secret scan. Print filenames/reasons, NEVER values.

This is a lightweight publication check, not a complete secret or PII detector.
Evaluation fixtures still require human review of their fictional provenance.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from nyaysaathi.settings import get_settings


PATTERNS = {
    "google_key": re.compile(r"(?:AIza[0-9A-Za-z_-]{30,}|AQ\.[0-9A-Za-z_-]{25,})"),
    "github_token": re.compile(r"(?:gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{30,})"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "aws_access_key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "vercel_token": re.compile(r"\bvcp_[A-Za-z0-9_]{25,}\b"),
    "credential_assignment": re.compile(r"(?:api[_-]?key|access[_-]?token|password)[\"']?\s*[:=]\s*[\"']([A-Za-z0-9_.+/=-]{28,})[\"']", re.IGNORECASE),
}


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True).stdout


def forbidden_path(name):
    path = Path(name)
    if any(part in {".venv", "venv", ".pytest_cache", ".vscode", ".vercel", "__pycache__"} for part in path.parts):
        return True
    return (path.name.startswith(".env") and path.name != ".env.example") or name == ".streamlit/secrets.toml" or path.suffix.lower() in {".pdf", ".pem", ".key", ".p12", ".pfx"} or path.name == "publication-audit.local.json" or (path.name.startswith("credentials") and path.suffix == ".json")


def scan(name, data, active_key):
    reasons = []
    if forbidden_path(name):
        reasons.append("private_or_local_path")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return [*reasons, "unreviewed_binary"]
    if active_key and active_key in text:
        reasons.append("active_key_present")
    for reason, pattern in PATTERNS.items():
        if pattern.search(text):
            reasons.append(reason)
    return reasons


def audit(history=False):
    key = get_settings().gemini_api_key
    findings = []
    names = git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z").decode().split("\0")
    staged = [name for name in names if name]
    for name in staged:
        reasons = scan(name, git("show", ":" + name), key)
        if reasons:
            findings.append({"file": name, "reasons": reasons, "location": "staged"})
    commits = git("rev-list", "--all").decode().splitlines() if history else []
    seen = set()
    for commit in commits:
        for line in git("ls-tree", "-r", commit).decode().splitlines():
            metadata, name = line.split("\t", 1)
            object_id = metadata.split()[-1]
            if (name, object_id) in seen:
                continue
            seen.add((name, object_id))
            reasons = scan(name, git("cat-file", "blob", object_id), key)
            if reasons:
                findings.append({"file": name, "reasons": reasons, "location": "history"})
    result = {"staged_files_scanned": len(staged), "commits_scanned": len(commits), "findings": findings}
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return not findings


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", action="store_true")
    args = parser.parse_args()
    raise SystemExit(0 if audit(args.history) else 1)
