#!/usr/bin/env python3
"""AST 强制应用层边界纪律（对 app/ 全量跑）。

规则对应 `.cursor/rules/app-layer-discipline.mdc` 与
`openspec/changes/refactor-app-layer-discipline/design.md` Decision 4 / 4b / 4c：

R1 `_*` 私有名不跨模块 —— `from <mod> import _x`（或 `import ..._x`）跨模块即违规。
R2 跨域 import 白名单 —— 跨域只碰对方 service 接口 / schemas / deps service-provider
   （`get_*_service`）；`require_admin` 是显式白名单例外（纯横切鉴权 gate，
   design Decision 4 引为先例，用户拍板：只返 uuid 不泄漏 ORM）。
R3 `get_current_*` 仅被本域 router 消费 —— 域内 current-object deps 被别域
   / 非 router 模块 import 即违规（infra `get_current_user_id` 共享基底豁免）。
R4 私有方法跨模块消费 —— `self.<注入实例>.<_private>`（在别模块对象上调用私有
   方法）即违规；被跨模块消费的方法必须公开（design Decision 4c）。

启发式结构规则（薄 router / 上帝 service）按 design 7.3 降为警告，本脚本暂不启用。

用法：`uv run python scripts/check_app_layer_discipline.py`；有违规时 exit 1。
"""

import ast
import pathlib
import sys

APP = pathlib.Path("app")
# 业务域（跨域纪律只作用于这些域之间；infra 是共享基底，任何域可 import）
DOMAINS = {"catalog", "ordering", "support", "user", "engagement", "media"}
# 跨域 deps import 白名单：service-provider（get_*_service）+ 显式例外 require_admin
# （纯横切鉴权 gate，design Decision 4 引为先例；用户拍板白名单例外）
CROSS_DOMAIN_DEPS_ALLOWED = {"require_admin"}


class _Finding:
    __slots__ = ("file", "line", "rule", "message")

    def __init__(self, file: str, line: int, rule: str, message: str) -> None:
        self.file = file
        self.line = line
        self.rule = rule
        self.message = message

    def __str__(self) -> str:
        return f"{self.file}:{self.line} [{self.rule}] {self.message}"


def _module_to_path(module: str) -> pathlib.Path | None:
    """把 ``app.a.b`` 解析为相对 app/ 的 .py 路径；非 app.* 或无对应文件返 None。"""
    if not module.startswith("app."):
        return None
    rel = module[4:].replace(".", "/")
    # 优先精确文件（app/a/b.py），否则按包（app/a/__init__.py）
    candidate = APP / f"{rel}.py"
    if candidate.exists():
        return candidate
    pkg = APP / rel / "__init__.py"
    if pkg.exists():
        return pkg
    return None


def _is_private_name(name: str) -> bool:
    return name.startswith("_")


def _is_service_module(submodule: str) -> bool:
    return submodule == "service" or submodule.endswith("_service")


def _is_service_provider(name: str) -> bool:
    # get_*_service（装配类 service-provider deps）
    return name.startswith("get_") and name.endswith("_service")


def _is_self_rooted(expr: ast.AST) -> bool:
    """表达式根是否为 ``self``（沿 Attribute 链下探）。"""
    while isinstance(expr, ast.Attribute):
        expr = expr.value
    return isinstance(expr, ast.Name) and expr.id == "self"


class AppLayerDisciplineChecker:
    """对单个 app/ 模块做规则检查。"""

    def __init__(
        self,
        rel: str,
        domain: str,
        tree: ast.Module,
        current_current_deps: dict[str, str],
    ) -> None:
        self.rel = rel
        self.domain = domain
        self.tree = tree
        self.current_current_deps = current_current_deps
        self.findings: list[_Finding] = []

    def _is_router_module(self) -> bool:
        return "router" in self.rel

    # ── R1 / R2：import 检查 ────────────────────────────────

    def check_imports(self) -> None:
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ImportFrom):
                self._check_import_from(node)
            elif isinstance(node, ast.Import):
                self._check_import(node)

    def _check_import_from(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        names = [a.name for a in node.names if a.name is not None]

        # R1：私有名不跨模块（含域内跨模块）
        for name in names:
            if _is_private_name(name):
                # 定位源模块；若无法定位则保守放行（相对导入等）
                if module.startswith("app."):
                    self._add(
                        node.lineno, "R1", f"跨模块 import 私有名 {module}.{name}"
                    )

        if not module.startswith("app."):
            return  # 非 app.* 导入（第三方 / 相对），不参与跨域白名单

        # 跨域白名单只作用于业务域模块之间；组合根（main.py）等非业务域模块豁免
        if self.domain not in DOMAINS:
            return

        parts = module[4:].split(".")
        src = parts[0]
        if src not in DOMAINS or src == self.domain:
            return  # 域内或非业务域（infra），白名单不适用

        submodule = parts[1] if len(parts) > 1 else ""
        # 跨域私有模块（路径含 _ 段）→ 违规
        if any(seg.startswith("_") for seg in parts):
            self._add(
                node.lineno,
                "R2",
                f"跨域 import 私有模块 {module}（白名单外）",
            )
            return

        if _is_service_module(submodule) or submodule == "schemas":
            return  # service 接口 / schemas，白名单内

        if submodule == "deps":
            bad = [
                n
                for n in names
                if not (_is_service_provider(n) or n in CROSS_DOMAIN_DEPS_ALLOWED)
            ]
            for n in bad:
                self._add(
                    node.lineno,
                    "R2",
                    f"跨域 import 对方 deps 非 service-provider {module}.{n}"
                    "（白名单：get_*_service / require_admin）",
                )
            return

        # models / repository / 其他模块 → 违规
        self._add(
            node.lineno,
            "R2",
            f"跨域 import {module}（白名单只放 service 接口 / schemas / service-provider deps）",
        )

    def _check_import(self, node: ast.Import) -> None:
        for alias in node.names:
            dotted = alias.name
            if dotted.startswith("app."):
                parts = dotted[4:].split(".")
                src = parts[0]
                if self.domain in DOMAINS and src in DOMAINS and src != self.domain:
                    # `import app.<域>.service` 等 —— 同样按白名单子模块判断
                    submodule = parts[1] if len(parts) > 1 else ""
                    if _is_service_module(submodule) or submodule == "schemas":
                        continue
                    self._add(
                        node.lineno,
                        "R2",
                        f"跨域 import {dotted}（白名单外）",
                    )
            if _is_private_name(dotted.rsplit(".", 1)[-1]) and not dotted.startswith(
                "app."
            ):
                self._add(node.lineno, "R1", f"import 私有名 {dotted}")

    # ── R3：get_current_* 仅被本域 router 消费 ───────────────

    def check_current_deps(self) -> None:
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ImportFrom):
                for name in node.names:
                    if name.name is None:
                        continue
                    def_domain = self.current_current_deps.get(name.name)
                    if def_domain is None:
                        continue
                    if def_domain != self.domain or not self._is_router_module():
                        self._add(
                            node.lineno,
                            "R3",
                            f"current-object deps `{name.name}` 仅被 {def_domain} 域 router 消费，"
                            f"此处（{self.rel}）违规",
                        )

    # ── R4：私有方法跨模块消费（self.X._private）────────────

    def check_private_attr_access(self) -> None:
        for node in ast.walk(self.tree):
            if (
                isinstance(node, ast.Attribute)
                and _is_private_name(node.attr)
                and isinstance(node.value, ast.Attribute)
                and _is_self_rooted(node.value)
            ):
                self._add(
                    node.lineno,
                    "R4",
                    f"在注入实例上调用私有成员 `{node.attr}`"
                    "（被跨模块消费的方法必须公开，design Decision 4c）",
                )

    def _add(self, line: int, rule: str, message: str) -> None:
        self.findings.append(_Finding(self.rel, line, rule, message))


def collect_current_deps() -> dict[str, str]:
    """收集所有域内 `get_current_*` deps 定义：name → 定义域。"""
    result: dict[str, str] = {}
    for py in APP.rglob("*.py"):
        if "__pycache__" in py.parts:
            continue
        rel = py.relative_to(APP).as_posix()
        domain = rel.split("/")[0]
        if domain not in DOMAINS:
            continue
        try:
            tree = ast.parse(py.read_text())
        except SyntaxError:
            continue
        for node in tree.body:
            # current-object deps 均为 async def → AsyncFunctionDef
            if isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef)
            ) and node.name.startswith("get_current_"):
                result[node.name] = domain
    return result


def main() -> int:
    current_deps = collect_current_deps()
    findings: list[_Finding] = []

    for py in sorted(APP.rglob("*.py")):
        if "__pycache__" in py.parts:
            continue
        rel = py.relative_to(APP).as_posix()
        domain = rel.split("/")[0]
        try:
            tree = ast.parse(py.read_text())
        except SyntaxError as exc:
            findings.append(_Finding(rel, 0, "SYNTAX", str(exc)))
            continue
        checker = AppLayerDisciplineChecker(rel, domain, tree, current_deps)
        checker.check_imports()
        checker.check_current_deps()
        checker.check_private_attr_access()
        findings.extend(checker.findings)

    if findings:
        print(f"error: 应用层边界纪律违规 {len(findings)} 处：")
        for f in findings:
            print(f"  {f}")
        return 1

    print(
        "ok: app/ 全量通过应用层边界纪律（R1 私有名 / R2 跨域白名单 / R3 current-deps / R4 私有方法）"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
