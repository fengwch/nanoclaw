# IPC 权限说明

## 什么是 IPC

NanoClaw 中 **IPC（进程间通信）** 指：**容器内 Agent** 通过**文件系统**向 **Host（宿主机）** 发起请求的机制。容器只能写约定目录下的 JSON 文件，Host 上的 **IPC Watcher**（`src/ipc.ts`）轮询这些文件并执行相应操作（发消息、建任务等），同时按**群组身份**做权限校验。

- **身份来源**：每个群的容器挂载的是**该群专属**的 IPC 目录 `data/ipc/{group_folder}/`，因此 Host 根据**文件所在目录**即可确定请求来自哪个群（主群或某个非主群）。
- **权限原则**：**主群**可管理所有群组与任务、向任意会话发消息；**非主群**仅能操作本群（本群会话、本群任务）。

---

## IPC 有哪些功能

### 1. 发消息（message）

| 项目 | 说明 |
|------|------|
| **类型** | `type: 'message'` |
| **写入位置** | 容器内 `/workspace/ipc/messages/`（对应 Host 的 `data/ipc/{group_folder}/messages/`） |
| **JSON 字段** | `chatJid`（目标会话 JID）、`text`（消息正文）、可选 `sender` |
| **Agent 调用方式** | MCP 工具 **`send_message`**（容器内 MCP 服务器 `nanoclaw` 提供） |

**权限**：

- 主群：可向**任意已注册会话**（`chatJid`）发消息。
- 非主群：仅可向**本群**的 `chatJid` 发消息；若写其他群的 JID，Host 会拒绝并打日志 `Unauthorized IPC message attempt blocked`。

---

### 2. 计划任务（tasks）

所有任务类请求都写入容器内 `/workspace/ipc/tasks/`（Host 上为 `data/ipc/{group_folder}/tasks/`），由 Host 解析 `type` 后执行对应逻辑。

| 功能 | IPC type | MCP 工具名 | 说明 |
|------|----------|------------|------|
| 创建计划任务 | `schedule_task` | **schedule_task** | 新建定时/周期任务（cron / interval / once） |
| 列出任务 | （读 Host 写入的 `current_tasks.json`） | **list_tasks** | 查看已计划任务列表 |
| 暂停任务 | `pause_task` | **pause_task** | 暂停指定 task_id |
| 恢复任务 | `resume_task` | **resume_task** | 恢复已暂停任务 |
| 取消任务 | `cancel_task` | **cancel_task** | 删除任务 |
| 更新任务 | `update_task` | **update_task** | 修改 prompt / 执行时间等 |
| 刷新群组元数据 | `refresh_groups` | （无单独工具，可由主群触发） | 主群专用，同步渠道群列表并写回 available_groups.json |
| 注册新群组 | `register_group` | **register_group** | 主群专用，将新会话注册为群组 |

**权限**：

- **主群**：可为任意已注册群创建/暂停/恢复/取消/更新任务；可 `refresh_groups`、`register_group`；`list_tasks` 看到全部任务。
- **非主群**：只能为本群创建任务（`targetJid` 只能是本群）、只能管理**本群所属**的任务（pause/resume/cancel/update 仅限本群 task）；不能 `register_group` 或 `refresh_groups`；`list_tasks` 只看到本群任务。

---

## 权限矩阵小结

| 操作 | 主群 | 非主群 |
|------|------|--------|
| 向本群发消息 | ✓ | ✓ |
| 向其他群发消息 | ✓ | ✗ |
| 为本群创建计划任务 | ✓ | ✓ |
| 为其他群创建计划任务 | ✓ | ✗ |
| 查看所有任务 | ✓ | 仅本群 |
| 暂停/恢复/取消/更新 本群任务 | ✓ | ✓ |
| 暂停/恢复/取消/更新 其他群任务 | ✓ | ✗ |
| 注册新群组（register_group） | ✓ | ✗ |
| 刷新群组元数据（refresh_groups） | ✓ | ✗ |

---

## 如何使用

### 在容器内（Agent 侧）

1. **通过 MCP 工具（推荐）**  
   容器内 Claude Agent 已挂载 **nanoclaw** MCP 服务器，可直接调用：
   - `send_message`：发消息到指定会话
   - `schedule_task` / `list_tasks` / `pause_task` / `resume_task` / `cancel_task` / `update_task`：计划任务全生命周期
   - `register_group`：主群注册新群（需提供 jid、name、folder、trigger 等）
   - `get_weather`：查天气（与权限无关，仅调用外部 API）

   工具名在 SDK 中显示为 `mcp__nanoclaw__<工具名>`（如 `mcp__nanoclaw__send_message`）。

2. **直接写 IPC 文件（不推荐）**  
   若绕过 MCP、自己写 JSON 文件到 `/workspace/ipc/messages/` 或 `/workspace/ipc/tasks/`，需遵守与 Host 相同的协议（见 `src/ipc.ts` 及 `container/agent-runner/src/ipc-mcp-stdio.ts`）。身份仍由**该群挂载的 IPC 目录**决定，权限规则同上。

### 在 Host 侧

- **轮询**：`src/ipc.ts` 的 `startIpcWatcher(deps)` 按 `IPC_POLL_INTERVAL`（默认 1 秒）扫描 `data/ipc/*/messages/` 和 `data/ipc/*/tasks/`，处理后删除已处理的 JSON 文件。
- **鉴权**：每条消息、每个任务请求都会用「当前 IPC 目录对应的群组」与「目标 JID / 目标任务所属群」做比较，非主群越权操作会被拒绝并打 warn 日志。

---

## 相关文件与配置

| 位置 | 说明 |
|------|------|
| `src/ipc.ts` | IPC Watcher：轮询、解析、鉴权、调用 sendMessage / 任务 DB |
| `src/config.ts` | `IPC_POLL_INTERVAL`（轮询间隔，默认 1000 ms） |
| `container/agent-runner/src/ipc-mcp-stdio.ts` | 容器内 MCP 服务：实现 send_message、schedule_task、list_tasks、pause/resume/cancel/update_task、register_group、get_weather 等 |
| `data/ipc/{group_folder}/messages/` | 该群「发消息」请求目录 |
| `data/ipc/{group_folder}/tasks/` | 该群「任务」请求目录 |
| `data/ipc/{group_folder}/input/` | Host → 容器：新消息与 `_close` 标记，供容器轮询 |

更多安全边界见 **docs/SECURITY.md**（含容器隔离、挂载白名单、凭证代理等）。
