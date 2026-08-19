# 集成测试 JWT iat 时钟回拨偶发 401

## 场景

全量测试（`task test` / `task ci`）**偶发**出现 401，错误为：

```text
The token is not yet valid (iat)
```

**区别于** [集成测试-JWT-Settings缓存与401.md](./集成测试-JWT-Settings缓存与401.md)（那是 **JWT 密钥不一致 / Settings 缓存** 导致的 401）；本文是 **时钟偏移** 导致的验签失败，根因、排查路径、修复完全不同。

## 现象（识别特征）

| 运行方式 | 结果 |
|----------|------|
| 单文件 / 单用例重跑 | **通过**（无法复现） |
| 全量 pytest | **偶发失败**，且每次失败的测试不同 |
| 探针加 print 后重跑 | **消失**（print 改变毫秒级时序，恰好避开回拨窗口——观察者效应） |

典型表现：

- 失败测试**不固定**：`test_delete_media_referenced_by_product_returns_409`、`test_create_root_category_success_returns_201`、`test_rate_limit_exceeded_returns_429` 等**不同测试**都偶发出现过 401
- 共同点：这些测试都走了 **`admin_auth_headers` / `authenticated_user` 等登录拿 token** 的鉴权链，且都调 **`POST /categories` / 带 Bearer 的业务请求**
- 日志里 **login 返回 200**（token 正常签发），但后续业务请求 401

> 因为它「单跑必绿、全量偶发、失败测试随机」，很容易被误判为：admin seed 缺失、require_admin 查库问题、或测试顺序污染。**真正的线索是错误文案 `The token is not yet valid (iat)`**——只在 decode 层出现。

## 根因

### 1. `iat` 是「截断到整数秒」的当前时间

`app/infra/auth.py::create_access_token`：

```python
now = datetime.now(UTC)
payload = {"sub": str(user_id), "iat": int(now.timestamp()), ...}
```

`int(now.timestamp())` 是 **floor 截断**。只要签发时刻落在整数秒 `N` 之后（哪怕晚 1 微秒），`iat` 就是 `N`。

### 2. pyjwt 校验 `iat` 时 `leeway` 默认为 0

`decode_access_token` 的 `jwt.decode(...)` 未传 `leeway` → 默认 `0`。校验逻辑：

```python
if iat > (now + leeway).timestamp():  # leeway=0
    raise ImmatureSignatureError("The token is not yet valid (iat)")
```

### 3. 系统时钟偶发回拨 → `iat` 短暂「在未来」

实测（探针打印 decode 时刻与 token 的 iat）：

```text
iat=1787146521 exp=1787148321 now_ts=1787146520.555482 err=The token is not yet valid (iat)
```

`iat` 比 decode 时刻 **未来 0.45–0.9 秒**。同一进程、毫秒间隔内 create 与 decode 的 `datetime.now(UTC)` 居然「倒退」——这是 **WSL / 沙箱 / 虚拟机时钟偶发回拨**（宿主时间同步、NTP 校正）导致。`create` 时 `now.timestamp() ≥ N+0`，紧接着 `decode` 时时钟回落到 `N-0.x`，`int()` 截断出的 `iat=N` 便大于解码时刻。

**不是**：测试 mock 时间（全文搜索无任何 `freezegun` / `datetime` patch）、token 跨测试缓存、admin seed 缺失。

## 排查过程（完整还原，含走过的弯路）

> 以下按实际排查顺序记录。目的是让未来再遇到「全量偶发 401」时，能快速跳过这些弯路直接命中根因。

### 阶段一：先排除「是不是我最近改动引入的」

初始现象是 `task test` 全量报 **6 failed**（media 域 5 个 `test_magic_bytes` + 1 个 `test_delete_referenced` 401）。前 5 个是另一个坑（`text/plain` 魔数兜底与测试期望漂移，见 `uv-index-403-tuna镜像.md` 之外的关联记录），关键在最后一个 401。第一反应是「是不是最近的 AI 域改动碰坏了 media 鉴权」，先排除：

1. `git log` + 改动范围核对：最近提交只动 `app/ai/**` 与 `openspec/tasks.md`，**与 media 鉴权链路完全不相交**。
2. 单独跑失败用例 `test_delete_media_referenced_by_product_returns_409` → **通过**。
3. 同文件其余 2 个测试一起跑 → **通过**。
4. 依次组合跑：`media` 全目录、`catalog + 该测试`、`ai + 该测试`、`engagement+infra+ops+ordering+user + 该测试` → **全部通过**。
5. 但全量 → 偶发 401，且**每次失败的测试不同**（`delete_referenced`、`admin_categories`、`rate_limit` 在不同轮次分别出现）。

**阶段结论**：单跑必绿、全量偶发、失败随机 → 是 **flaky**。不是测试逻辑、不是顺序污染（所有目录组合都绿）、不是我的改动。**此时先别急着改代码，先怀疑环境/全局共享状态。**

### 阶段二：排除「数据库 / admin 数据」层（走了弯路但必要）

最自然的假设：401 来自 `require_admin` 的「`get_by_id` 查不到用户 → 401」。逐条验证：

1. 直接查测试库 `users` 表：`13800000000`（seed admin）**存在**，`is_admin=1`。
2. 真实 HTTP 登录：`POST /auth/login` → **200**，token `sub` = `d818d1bf-...`（正确指向 admin）。
3. 独立连接 `UserRepository.get_by_id(d818d1bf)` → **返回 admin**（`is_admin=True`）。
4. 模拟测试的 SAVEPOINT session 再做一次 `get_by_id` → **也返回 admin**。
5. **真实环境（真实 `get_db`，无 override）直接 `POST /categories` → 201 成功**！

**阶段结论**：数据层、真实请求全部正常，但测试环境全量下 401 → **自相矛盾**。这强烈暗示问题不在数据查询，而在 **token 本身**（decode 层）。—— 这一步排查很耗时，但如果一开始就意识到「login 200 但业务 401」说明 token 签发成功却验签失败，可以更早转向 decode 层。

### 阶段三：探针区分 401 出自哪一层（决定性一步）

`require_admin` 返回 401 有两条路径：

- `get_current_user_id`（`decode_access_token` 验签失败）
- `get_by_id` 返回 `None`（查库不到）

两条都叫 `HTTPException(401)`，光看日志 `code=UNAUTHORIZED` 分不清。用探针：

1. 先在 `require_admin` 的 `user is None` 分支加 `print` → 全量跑 → **探针未触发**。→ 排除「查库层」，401 来自更早的 `get_current_user_id`。
2. 改在 `decode_access_token` 的 `except InvalidTokenError` 加 `print(token)` → 全量跑 → **`DIAG decode FAILED ... err=The token is not yet valid (iat)`**。→ **实锤 401 来自验签**，且错误指向 `iat`。
3. 打印更详细（不验签解码 payload + 当前时间戳）：

   ```python
   payload = jwt.decode(token, options={"verify_signature": False})
   print(f"iat={payload.get('iat')} now={datetime.now(UTC).timestamp()}", flush=True)
   ```

   得到：

   ```text
   iat=1787146521 exp=1787148321 now_ts=1787146520.555482
   ```

   → **`iat` 比 `now_ts` 大 0.45–0.9 秒**，`iat` 在未来，与错误文案完全吻合。

### 阶段四：观察者效应 + 排除「时间来自 mock」

1. **观察者效应**：加了 `print` 探针后重跑全量 → **全绿**（exit 0）。`print` 的 I/O 改变了毫秒级时序，恰好避开了时钟回拨窗口——**探针本身改变了被测现象**。取证时注意：探针输出应尽量轻（`flush=True`、少打印），或接受「多跑几次才复现」。
2. **排除「测试 mock 时间」**：全仓搜 `freezegun` / `datetime.now` / `monkeypatch` / `@patch` → 只有 2 处无关 mock（`test_readiness` 连探、`test_embedder` 注入 embedder），**无任何时间 mock**。
3. **排除「token 缓存」**：testkit 无 token 缓存，`authenticated_user` / `admin_auth_headers` 每次 `login` 新签发，不跨用例复用。

**阶段结论**：时间没有被 mock、token 没有复用 → create 与 decode 用的是同一个 `datetime.now(UTC)`，却在毫秒内「倒退」——只剩 **系统时钟回拨** 一个解释。

### 阶段五：根因链条收拢

```text
create_access_token: iat = int(now.timestamp())   # floor 截断，落在整数秒 N 之后即 iat=N
        │
        ▼  （WSL/沙箱时钟偶发回拨，decode 时刻 datetime.now 回落到 N-0.x 秒）
decode_access_token: jwt.decode(..., leeway=0)    # iat > now.timestamp() → 拒绝
        │
        ▼
HTTP 401 "The token is not yet valid (iat)"
```

**同一进程内 `datetime.now` 毫秒间隔「倒退」，代码层面无法消除**（时钟回拨是环境行为）——只能靠解码侧 `leeway` 容错。

## 修复

`app/infra/auth.py::decode_access_token` 的 `jwt.decode` 加 **`leeway=5`**：

```python
payload = jwt.decode(
    token,
    settings.jwt_secret_key,
    algorithms=[settings.jwt_algorithm],
    issuer=settings.jwt_issuer,
    # 容忍时钟偏移/回拨（iat 微幅未来 / exp 微幅已过）
    leeway=5,
)
```

- **为什么是 5 秒**：实测回拨幅度 0.5–1 秒；5 秒是 JWT 场景常见容错值，既不放松「过期」语义（exp 最多宽容 5 秒），又覆盖本机时钟抖动。
- **为什么不改 create**：`int(now.timestamp())` 已是最安全的 floor 截断；问题在 decode 校验过严（`leeway=0`），不是签发方。
- **为什么不 mock 时间 / 修单个测试**：根因是环境时钟，与具体测试无关，修 decode 是全局、标准、向后兼容的解法。

## 复现

### 复现思路：验签层的等价条件

失败条件本质是 `iat > decode_now`。一次幅度 `S` 的时钟回拨会让 decode 时刻的墙钟比 iat 小 `S`——这在验签层与「签发时 `iat` 比真实时间多 `S` 秒」**是同一个条件**（pyjwt 只比较 `iat` 与它自己取的 `datetime.now(timezone.utc)`）。因此不需要 mock 任何代码，直接用「iat 在未来 ~1s」的合法 token 即可精确复现探针实测的错误文案。

### 确定性复现（✅ 成功，可随时重跑）

```python
# APP_ENV_FILE=.env.test uv run python repro.py
import os, sys, uuid
from datetime import UTC, datetime, timedelta
os.environ["APP_ENV_FILE"] = ".env.test"
import jwt
from jwt.exceptions import ImmatureSignatureError
from app.infra.auth import create_access_token, decode_access_token
from app.infra.config import get_settings

settings = get_settings()
USER = uuid.uuid4()
SKEW = 1  # 模拟回拨幅度 ~1s（探针实测 0.45–0.9s）

def decode_pre_fix(token):  # 复刻修复前：leeway 默认 0
    return jwt.decode(token, settings.jwt_secret_key,
                      algorithms=[settings.jwt_algorithm], issuer=settings.jwt_issuer)

def make_skewed_token(offset_s):  # iat 在未来 offset_s 秒（回拨等效条件）
    now = datetime.now(UTC)
    payload = {"iss": settings.jwt_issuer, "sub": str(USER),
               "iat": int(now.timestamp()) + offset_s,
               "exp": int((now + timedelta(minutes=30)).timestamp()), "typ": "access"}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

tok, _ = create_access_token(USER)      # 0. 基线
assert decode_access_token(tok) == USER

tok_s = make_skewed_token(SKEW)
try:
    decode_pre_fix(tok_s)               # 1. pre-fix：应精确复现 401 根因
    raise SystemExit("意外通过")
except ImmatureSignatureError as e:
    print("✅ 复现 pre-fix 根因:", e)     # → The token is not yet valid (iat)

print("✅ 修复后通过:", decode_access_token(tok_s))  # 2. leeway=5 容忍
try:
    decode_access_token(make_skewed_token(6))        # 3. 边界：6s > leeway
    raise SystemExit("6s 应被拒绝")
except Exception:
    print("✅ 6s 回拨仍被拒绝 → 安全边界未破坏")
```

实际输出（与探针文案逐字一致）：

```text
✅ 复现 pre-fix 根因: The token is not yet valid (iat)
✅ 修复后通过: b2a45453-...
✅ 6s 回拨仍被拒绝 → 安全边界未破坏
```

**复现结论**：`iat` 在未来 ~1s 的 token，在修复前（`leeway=0`）必然抛出与探针相同的错误；修复后（`leeway=5`）同一 token 通过；回拨超过 leeway 仍拒绝——证明修复只放宽标准容差，不破坏过期语义。

### 自然复现尝试（⚠️ 90s 未命中，属正常）

为直接观测环境回拨，高速采样 `time.time()`（42 万次/90s）**未检测到真实倒退**。这与「回拨是低频偶发」一致（分钟级到几十分钟才一次，90s 窗口大概率抓不到），**不否定根因**——原始探针已在真实全量运行中实测过 `iat` 未来 0.45s。若想抓环境实证：`journalctl -f | grep -iE "step|timesync"` 与失败时间戳对齐，或拉长监控窗口。

## 原理深挖：leeway 与虚拟化时钟回拨

### leeway 是什么

JWT 携带三个时间戳声明，decode 时 PyJWT 用**验证时刻的墙钟**逐一比对：

| 声明 | 含义 | 不加 leeway 的校验 | 加 leeway=5 |
|------|------|-------------------|-------------|
| `iat` | 签发时刻 | `now >= iat` | `now >= iat - 5` |
| `exp` | 过期时刻 | `now <= exp` | `now <= exp + 5` |
| `nbf` | 最早生效时刻 | `now >= nbf` | `now >= nbf - 5` |

`leeway`（宽容度）就是把这些**刚性边界**整体放宽 `N` 秒。默认 `0` 意味着 `now` 比 `iat` 早哪怕 0.1 秒也判失败；`leeway=5` 后 `now` 比 `iat` 早最多 5 秒仍通过。

它不是 hack，而是对现实的正确定模：**任何系统里签名端与验证端的墙钟都不可能完美同步**（同一进程也会受系统时钟回拨影响）。RFC 7519 明确允许实现留少量时钟容差，PyJWT 的 `leeway` 参数就是标准出口。

### 为什么虚拟化层的墙钟会「回拨」

**墙钟 vs 单调钟**：

| 类型 | 是什么 | 会不会倒退 |
|------|--------|-----------|
| 墙钟（wall clock） | `datetime.now()` / `time.time()`，现在几点 | **会**，被 NTP 等对表时可往前拨 |
| 单调钟（monotonic clock） | `time.monotonic()`，开机起只增不减 | 永不倒退 |

JWT 签发/验证需要「双方都认可的墙上时间」，**只能用墙钟**——所以无法用单调钟规避这个问题，只能容忍墙钟的缺陷。

**墙钟为什么会倒退**：系统时间长期漂移，NTP 对表发现偏差后有两条校正路径：

```
slew（渐变）: 偏差小，让钟走快/走慢一点，时间线连续，无「倒退」
step（跳变）: 偏差超阈值（Linux 默认 ~128ms），直接把时间拨到正确值
             10:00:00.200 → 10:00:00.050   ← 「回拨」，time.time() 变小
```

**WSL2 特别容易触发**（它不是 WSL1 的系统调用翻译层，是跑在 Hyper-V 上的真虚拟机）：

1. **时钟来源是模拟的**：虚拟机的 TSC / RTC 由虚拟化层模拟，精度不如物理硬件，长期漂移更大 → 更容易超过 step 阈值
2. **挂起/恢复巨大偏差**：Windows 睡眠时虚拟机停走，醒来后时间落后一大截，同步服务大步往前拨
3. **两层对表**：Hyper-V 时间同步服务周期对齐到宿主机 Windows，Windows 又经 NTP 对齐到 time.windows.com——每一层都是潜在回拨源
4. **WSL2 是已知「漂移大户」**：微软官方有 WSL 睡眠后时钟不同步的已知问题（如 microsoft/WSL#4245）

**为什么「偶发」**：校正动作随机发生，只有恰好撞进 `iat 签发 → 验证` 之间的毫秒窗口才翻车；探针 `print` 改变毫秒时序即可避开 → 观察者效应。

**一句话**：回拨是虚拟化对表时的物理现实，代码层无法消除；`leeway` 是对这个现实的正确建模，而非规避。

## 与其他 401 成因的区分

| 401 成因 | 错误文案 / 特征 | 排查 |
|----------|----------------|------|
| JWT 密钥不一致 / Settings 缓存 | 一般性 `InvalidSignatureError` 或验签失败 | 见 [JWT-Settings 缓存 401](./集成测试-JWT-Settings缓存与401.md) |
| `require_admin` 查无用户 | `Could not validate credentials`（decode 通过，查库 None） | 检查 seed admin / migrate |
| 空 `headers` / 未带 Bearer | 请求压根没 token | 检查 Context 半成功 |
| **时钟回拨（本文）** | **`The token is not yet valid (iat)`** | 见上文阶段三探针取证 |

## 关键概念

- **`iat`（Issued At）**：签发时间戳；`int(now.timestamp())` 截断到整数秒，存在「刚过整数秒边界」的敏感窗口
- **pyjwt `leeway`**：容忍 `iat`/`exp` 与本地时钟的偏移秒数；默认 0，即完全不宽容
- **时钟回拨**：WSL/沙箱/虚拟机偶发，create 与 decode 毫秒间隔内 `datetime.now` 倒退——进程内无法用代码消除，只能靠 `leeway` 容错
- **观察者效应**：探针 `print` 改变毫秒时序可掩盖问题，取证时注意
- **「单跑绿 + 全量偶发 + 失败随机」三件套**：先怀疑全局共享状态（时钟 / 连接池 / 环境），不要急着改测试或业务代码

## 关联文件

- `app/infra/auth.py` — `create_access_token`（`int(now.timestamp())`）、`decode_access_token`（加 `leeway=5`）
- `app/user/deps.py` — `require_admin`（401 的另一路径：查库 None，用于阶段三区分）
- `docs/troubleshooting/集成测试-JWT-Settings缓存与401.md` — 相邻 401 成因（密钥/缓存），勿混淆
