"""#67/#68 的静态锁：SDK 生产代码不得再调用 asyncio.wait_for。

CPython ≤3.11 的 asyncio.wait_for 在「被等待的 Future 完成与 task.cancel() 落在同一 tick」
时会吞掉取消（asyncio/tasks.py：except CancelledError: if fut.done(): return fut.result()），
等待方随后进入下一轮全新等待，而那次取消已被消费，于是外层 gather 永久挂起。
3.12 重写了该分支，但下游生产解释器是 3.11，因此本锁与解释器无关：只要生产路径出现
wait_for 调用就判红。注释或字符串里提到历史缺陷不受影响，AST 只看 ast.Call。
"""
from __future__ import annotations

import ast
from pathlib import Path

SDK_PACKAGE = Path(__file__).resolve().parents[1] / "sdk" / "capswriter_asr"


def _wait_for_calls(tree: ast.AST) -> list[ast.Call]:
    """收集形如 asyncio.wait_for(...) / wait_for(...) 的调用节点。"""
    hits: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute):
            name = func.attr
        elif isinstance(func, ast.Name):
            name = func.id
        else:
            continue
        if name == "wait_for":
            hits.append(node)
    return hits


def test_sdk_package_never_calls_wait_for():
    offenders: list[str] = []
    for source in sorted(SDK_PACKAGE.rglob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for call in _wait_for_calls(tree):
            offenders.append(f"{source.relative_to(SDK_PACKAGE.parents[1])}:{call.lineno}")

    assert offenders == [], "生产路径不得调用会吞取消的 asyncio.wait_for：\n" + "\n".join(
        offenders
    )


def test_lock_detects_a_planted_wait_for_call():
    """判据自检：把 wait_for 塞回源码，扫描器必须转红；注释/字符串提到它不算（恒真断言等于没写）。"""
    planted = "import asyncio\n\nasync def f():\n    await asyncio.wait_for(x(), timeout=1)\n"
    assert len(_wait_for_calls(ast.parse(planted))) == 1

    # 注释与 docstring 提到历史缺陷、以及只引用不调用，都不该被判红。
    mentioned_only = (
        "import asyncio\n\n"
        'async def f():\n'
        '    """曾用 asyncio.wait_for（有吞取消缺陷）。"""\n'
        "    # 不要再写 asyncio.wait_for\n"
        "    return asyncio.wait_for\n"
    )
    assert _wait_for_calls(ast.parse(mentioned_only)) == []