# coding: utf-8
"""GPU 加速权限检测：POSIX 上 root 必须被识别为管理员。"""
import os

import pytest

from core.server.worker.gpu_boost import GpuBoostManager


@pytest.mark.skipif(os.name == "nt", reason="POSIX euid 检测")
def test_check_admin_true_when_euid_is_root(monkeypatch):
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    assert GpuBoostManager._check_admin() is True


@pytest.mark.skipif(os.name == "nt", reason="POSIX euid 检测")
def test_check_admin_false_when_euid_is_unprivileged(monkeypatch):
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    assert GpuBoostManager._check_admin() is False
