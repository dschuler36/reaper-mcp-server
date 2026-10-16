"""Regression tests for issue #12: tools must not open files outside the projects dir."""

import os

import pytest

from reaper_mcp_server.audio_analyzer import AudioAnalyzer
from reaper_mcp_server.utils import resolve_project_path


@pytest.fixture
def layout(tmp_path):
    projects = tmp_path / 'projects'
    (projects / 'song').mkdir(parents=True)
    inside = projects / 'song' / 'song.RPP'
    inside.write_text('<REAPER_PROJECT\n>\n')
    outside = tmp_path / 'outside.RPP'
    outside.write_text('<REAPER_PROJECT\n>\n')
    return projects, inside, outside


def test_accepts_project_inside_dir(layout):
    projects, inside, _ = layout
    assert resolve_project_path(str(inside), str(projects)) == os.path.realpath(inside)


def test_accepts_lowercase_extension(layout):
    projects, _, _ = layout
    lower = projects / 'song' / 'other.rpp'
    lower.write_text('<REAPER_PROJECT\n>\n')
    assert resolve_project_path(str(lower), str(projects)) == os.path.realpath(lower)


def test_rejects_dotdot_traversal(layout):
    projects, _, _ = layout
    with pytest.raises(ValueError, match='outside the projects directory'):
        resolve_project_path(str(projects / '..' / 'outside.RPP'), str(projects))


def test_rejects_absolute_path_elsewhere(layout):
    projects, _, _ = layout
    with pytest.raises(ValueError, match='outside the projects directory'):
        resolve_project_path('/etc/passwd', str(projects))


def test_rejects_symlink_out_of_dir(layout):
    projects, _, outside = layout
    link = projects / 'link.RPP'
    link.symlink_to(outside)
    with pytest.raises(ValueError, match='outside the projects directory'):
        resolve_project_path(str(link), str(projects))


def test_rejects_sibling_with_shared_prefix(tmp_path):
    projects = tmp_path / 'projects'
    projects.mkdir()
    sibling = tmp_path / 'projects-evil'
    sibling.mkdir()
    target = sibling / 'x.RPP'
    target.write_text('')
    with pytest.raises(ValueError, match='outside the projects directory'):
        resolve_project_path(str(target), str(projects))


def test_rejects_non_rpp_file_inside_dir(layout):
    projects, _, _ = layout
    notes = projects / 'notes.txt'
    notes.write_text('hi')
    with pytest.raises(ValueError, match=r'Not a Reaper project'):
        resolve_project_path(str(notes), str(projects))


def test_rejects_when_projects_dir_unset(layout):
    _, inside, _ = layout
    with pytest.raises(ValueError, match='not configured'):
        resolve_project_path(str(inside), None)


def test_analyzer_refuses_non_audio_file(tmp_path):
    secret = tmp_path / 'secret.txt'
    secret.write_text('not audio')
    result = AudioAnalyzer(str(secret)).analyze()
    assert result.error.startswith('Unsupported audio file type')


def test_analyzer_does_not_probe_existence_of_non_audio(tmp_path):
    missing = tmp_path / 'missing.key'
    result = AudioAnalyzer(str(missing)).analyze()
    assert result.error.startswith('Unsupported audio file type')
    assert 'not found' not in result.error
