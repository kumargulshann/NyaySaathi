"""Offline publication/configuration checks; no external network requests."""
import json
from pathlib import Path
import subprocess
import tomllib

from fastapi.testclient import TestClient

from backend.main import app
from nyaysaathi.knowledge import load_knowledge
from scripts.audit_publication import forbidden_path, scan


ROOT=Path(__file__).resolve().parents[1]


def test_explicit_entrypoint_dependencies_and_deploy_exclusions():
    project=tomllib.loads((ROOT/'pyproject.toml').read_text(encoding='utf-8'))
    assert project['tool']['vercel']['entrypoint']=='backend.main:app'
    assert not any(item.startswith(('streamlit','pytest')) for item in project['project']['dependencies'])
    config=json.loads((ROOT/'vercel.json').read_text(encoding='utf-8'))
    settings=config['functions']['backend/main.py']
    assert settings['maxDuration']>=55
    assert '.env' in settings['excludeFiles']
    assert 'legal_knowledge.json' not in settings['excludeFiles']
    assert (ROOT/'web/index.html').is_file()
    assert (ROOT/'nyaysaathi/data/legal_knowledge.json').is_file()


def test_routes_and_knowledge_do_not_depend_on_working_directory(monkeypatch,tmp_path):
    monkeypatch.chdir(tmp_path)
    load_knowledge.cache_clear()
    assert load_knowledge()
    with TestClient(app) as client:
        for path in ('/','/api/health','/static/app.js','/static/styles.css','/static/audio.js','/static/pcm-worklet.js'):
            assert client.get(path).status_code==200


def test_publication_scan_blocks_secrets_and_private_files_without_echoing_values():
    assert forbidden_path('.env') and forbidden_path('.streamlit/secrets.toml')
    assert forbidden_path('Kuku — AI Generalist Assignment.pdf')
    assert not forbidden_path('.env.example')
    key='offline-'+'x'*40
    reasons=scan('web/bad.js',key.encode(),key)
    assert reasons==['active_key_present']
    assert key not in str(reasons)
    assert not scan('.env.example',b'GEMINI_API_KEY=your_api_key_here',None)
