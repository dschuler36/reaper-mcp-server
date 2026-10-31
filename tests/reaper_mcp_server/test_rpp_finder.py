"""Tests for project discovery, including case-insensitive extension matching.

Reaper writes the project extension in lowercase (``song.rpp``) on current
versions, while older projects and templates use ``song.RPP``. Discovery has to
accept both, and `resolve_project_path` already does -- see
test_path_safety.test_accepts_lowercase_extension.
"""

import os

import pytest

from reaper_mcp_server.rpp_finder import RPPFinder


@pytest.fixture
def projects_dir(tmp_path):
    projects = tmp_path / 'projects'
    projects.mkdir()
    return projects


def _write_project(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('<REAPER_PROJECT\n>\n')
    return path


def _names(projects):
    return sorted(p['project_name'] for p in projects)


def test_finds_uppercase_extension(projects_dir):
    _write_project(projects_dir / 'song.RPP')
    assert _names(RPPFinder(str(projects_dir)).find_reaper_projects()) == ['song']


def test_finds_lowercase_extension(projects_dir):
    """Reaper saves lowercase .rpp, so discovery must not be case-sensitive."""
    _write_project(projects_dir / 'song.rpp')
    assert _names(RPPFinder(str(projects_dir)).find_reaper_projects()) == ['song']


def test_finds_mixed_case_extension(projects_dir):
    _write_project(projects_dir / 'song.Rpp')
    assert _names(RPPFinder(str(projects_dir)).find_reaper_projects()) == ['song']


def test_finds_projects_regardless_of_case(projects_dir):
    _write_project(projects_dir / 'lower.rpp')
    _write_project(projects_dir / 'upper.RPP')
    assert _names(RPPFinder(str(projects_dir)).find_reaper_projects()) == ['lower', 'upper']


def test_ignores_backup_files(projects_dir):
    """.rpp-bak files are Reaper's own backups, not projects to open."""
    _write_project(projects_dir / 'song.rpp')
    _write_project(projects_dir / 'song.rpp-bak')
    _write_project(projects_dir / 'song.RPP-bak')
    assert _names(RPPFinder(str(projects_dir)).find_reaper_projects()) == ['song']


def test_ignores_unrelated_files(projects_dir):
    _write_project(projects_dir / 'song.rpp')
    (projects_dir / 'notes.txt').write_text('hi')
    (projects_dir / 'take.wav').write_bytes(b'')
    assert _names(RPPFinder(str(projects_dir)).find_reaper_projects()) == ['song']


def test_recurses_into_subdirectories(projects_dir):
    _write_project(projects_dir / 'album' / 'track1' / 'track1.rpp')
    found = RPPFinder(str(projects_dir)).find_reaper_projects()
    assert len(found) == 1
    assert found[0]['project_name'] == 'track1'
    assert found[0]['directory'] == os.path.join('album', 'track1')
    assert found[0]['path'] == str(projects_dir / 'album' / 'track1' / 'track1.rpp')


def test_returns_empty_list_when_no_projects(projects_dir):
    assert RPPFinder(str(projects_dir)).find_reaper_projects() == []
