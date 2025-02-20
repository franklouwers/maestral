# -*- coding: utf-8 -*-

import os.path as osp

import pytest

from maestral.utils.path import (
    normalized_path_exists,
    equivalent_path_candidates,
    denormalize_path,
    is_fs_case_sensitive,
    is_child,
)
from maestral.utils.appdirs import get_home_dir


def test_path_exists_case_insensitive():

    # choose a path which exists on all Unix systems
    path = "/usr/local/share"

    assert denormalize_path(path) == path
    assert denormalize_path(path.title()) == path
    assert denormalize_path(path.upper()) == path

    # choose a random path that likely does not exist
    path = "/usr/local/share/test_folder/path_928"
    if not osp.exists(path):
        assert not normalized_path_exists(path)

    # choose a random parent that likely does not exist
    path = "/test_folder/path_928"
    root = "/usr"
    if not osp.exists(root):
        assert not normalized_path_exists(path, root)


def test_cased_path_candidates():

    # test that we can find a unique correctly cased path
    # starting from a candidate with scrambled casing

    path = "/usr/local/share".upper()
    candidates = equivalent_path_candidates(path)

    assert len(candidates) == 1
    assert "/usr/local/share" in candidates

    candidates = equivalent_path_candidates("/test", root="/usr/local/share")

    assert len(candidates) == 1
    assert "/usr/local/share/test" in candidates


@pytest.mark.skipif(
    not is_fs_case_sensitive(get_home_dir()),
    reason="requires case-sensitive file system",
)
def test_multiple_cased_path_candidates(tmp_path):

    # test that we can get multiple cased path
    # candidates on case-sensitive file systems

    # create two folders that differ only in casing

    dir0 = tmp_path / "test folder/subfolder"
    dir1 = tmp_path / "Test Folder/subfolder"

    dir0.mkdir(parents=True, exist_ok=True)
    dir1.mkdir(parents=True, exist_ok=True)

    dir0 = str(dir0)
    dir1 = str(dir1)

    # scramble the casing and check if we can find matches
    path = osp.join(dir0.lower(), "File.txt")

    # find matches for original path itself
    candidates = equivalent_path_candidates(path)

    assert len(candidates) == 2
    assert osp.join(dir0, "File.txt") in candidates
    assert osp.join(dir1, "File.txt") in candidates

    # find matches for children
    candidates = equivalent_path_candidates(
        "/test folder/subfolder/File.txt", root=str(tmp_path)
    )

    assert len(candidates) == 2
    assert osp.join(dir0, "File.txt") in candidates
    assert osp.join(dir1, "File.txt") in candidates


def test_is_child():
    assert is_child("/parent/path/child", "/parent/path/")
    assert is_child("/parent/path/child/", "/parent/path")
    assert not is_child("/parent/path", "/parent/path")
    assert not is_child("/path1", "/path2")
