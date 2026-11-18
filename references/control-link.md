# USB 控制服务与开发闭环

复用 autodam 独立 daemon 和 iOS MCP，不注入应用。`scripts/link.py` 是 CLI 和标准输入输出 MCP 服务共用的实现。它通过 `idevice_id` 找到已配对 USB 设备，使用已有 `iproxy` 把设备 8090 转到随机本机回环端口，协商真实工具列表，再从 `get_app_info` 返回的应用路径发现 `autodamd --bridge-info`。所有状态目录取自该接口；不猜 RootHide UUID、容器目录或 IP。

运行器必须具有 control protocol 1（从 autodam 0.3.0 开始），当前设备已安装 0.3.6；新版首页、折叠设置与原生区域 OCR 已真机验证，华硕完整回归停在小程序分类转场，不能标记全流程通过。MCP 文件和命令工具必须已由用户启用。多台设备用 `--udid`，也可通过 `--mcp-url http://127.0.0.1:PORT/mcp` 复用现有连接。工具只绑定回环，不开公网服务。连接、读脚本和日志不先调用屏幕接口，也不自动按 Home；执行前由原生运行器检查唤醒和锁屏状态。若设备 MCP 在锁屏时拒绝命令通道，需要先解锁，不能绕过身份验证。

## 读取和部署

在 Skill 根目录执行：

```sh
python3 scripts/link.py discover
python3 scripts/link.py read --args '{"flow_id":"autodam-storm-task"}'
python3 scripts/link.py status
```

`read` 返回当前完整 `flow` 与 `revision` 并自动保存到电脑私有目录。修改这份实际流程，保留用户的校准与已有步骤。将操作参数写入私有 JSON 文件后部署：

```json
{"flow":{"id":"existing-flow-id","name":"已有流程","blocks":[]},"expected_revision":"read 返回的版本"}
```

这是参数形状，空 blocks 不能运行。新增流程使用独立 ID 和 `expected_revision: "absent"`。执行：

```sh
python3 scripts/link.py deploy --args-file /private/path/deployment.json
```

daemon 在空闲时校验功能块，检查旧版摘要，先把旧流程保存到设备 `script-backups`，再提交配置并回读。响应包括新 revision、backup_id 和 readback 结果。已存在流程的定时开关和间隔保留，新流程不自动开启定时。版本冲突时重新读取、合并本次修改，不覆盖他人的版本。`rollback` 提供 flow_id、expected_revision、backup_id，恢复备份中的旧流程，同样产生一份新备份。用户删除和计划启停仍用原生编辑器。

## 执行和控制

```sh
python3 scripts/link.py run --args '{"flow_id":"existing-flow-id","expected_revision":"部署返回的版本"}'
python3 scripts/link.py watch --args '{"nonce":"run 返回的 nonce","seconds":180}'
```

run 走现有本地手动测试队列，不请求业务数据 API。运行快照被冻结，之后的编辑不改变已运行的步骤。status 分开返回请求 `manual` 和执行 `runtime`；`runtime.run_id` 用于 pause/resume/stop/fetch。pause 先返回 pause_requested，到下一设备调用边界确认 paused。已发出的设备操作无法撤销。resume 继续存活任务；进程重启或执行已结束时不能凭旧 ID 恢复，先核查业务副作用再决定重跑。stop 返回 stop_requested，确认最终 stopped 后才算已停止。

每次请求先保存 UUID 到电脑 requests。网络中断后以同一 request_id 再查询；不要为一次未确认的启动生成新 ID。结果未知时先 status 与页面复核，签到动作不盲目重放。

watch 到终态后自动 fetch：现有 OCR、页面图、日志、登录检查和同一运行的业务记录回传到 `~/Library/Application Support/autodam-link/`。默认目录权限 0700，文件 0600；不在 Skill/Git 工作树。设备上的原件保留在实际 state_directory。业务 receipt 与执行 succeeded 必须分别确认。

## 页面与录制

- `sample`：立即取当前页的真实图像/AX/OCR，回传私有目录；密码、验证码页只保留受限元数据。
- `capture`：调用设备原有延时采样模块，自动拉回结果。
- `recorder`，`command: start|stop|status|annotate`：操作现有录制模块。开始新录制前自动归档旧录制和预览；不得同时跑业务流程。annotate 参数为 frame、note、可选 tap_pt。
- `recording_fetch`：自动回传录制帧、OCR/AX、标注与预览。不把观察到的页面误认为已记录真实手指触摸。
- `learn`：自动取得已停止的原生录制，生成私有页面图、定位候选、登录变化、缺失项和标准功能块候选。参数为 flow_id、name、可选 final_keyword；详见 [录制学习](recording-learning.md)。
- `device`：通过发现的 iOS MCP UI 工具探索新页面。参数是 name 与 arguments；先根据当前工具 schema 构造。优先 sample，不直接在终端打印含个人信息的整页数据。

运行中的页面库保存于 `runs/RUN_ID/page-NNN`。0.3.5 普通运行的 `page.json` 为 `capture_mode: text_only`：保存名称、执行时已有 OCR、逻辑尺寸、时间和对应功能块，`ax` 为空，不额外请求截图或 OCR。完整截图与 AX 需显式 `sample` / `capture` / `recorder`，失败诊断仍保留；文件实际存在时 fetch 才回传。此前版本的完整运行样本仍可读取。`pages.json` 包含页面节点和有方向的跳转及实际设备动作。相同观察复用节点。AX 在微信里可能滞后，不能单独作为定位依据。样本只涵盖本次实际到达的页面；未触发的初次授权/首次领奖明确列为未采集。

## AI 的修复步骤

先读取已验证基线、实际流程及相关私有样本。只探索变化页。初次遇到需求时先列业务终点与副作用；再按真实页面构造标准功能块。部署 → run → watch → 检查结构化状态、同一笔业务回执与样本。失败时根据最后成功页面、预期锚点、错误和截图修改最小一段，再部署新版本。最多两次相同失败后切换诊断，不无限点击。验证码、未知授权、应用缺失、断线、系统限制保留原因并报告，不能制造成功。

登录通常先到右下角“我的”。登录提示证明 logged_out；账户身份标志才能确认 logged_in，仅看不到“登录”不能证明登录。unconfirmed 需要进一步读取账号页或业务状态。已有会话优先复用，不为测试退出账户。已获用户授权的一键登录可继续；验证码由用户完成。完成后重新读“我的”并保存结果。

## MCP stdio

```sh
python3 scripts/link.py serve
```

服务提供 `autodam` 工具：operation 选择以上操作，arguments 放参数。initialize、tools/list、tools/call 与 ping 可直接由 MCP 客户端调用。先确认本地依赖与真机再接入 AI 客户端；只编写 server 不能算端到端通过。

新增经验由 AI 依据真实样本提取稳定语义、成功条件和定位方法。人工复核脱敏后的这些规则可以更新 GitHub Skill；截图、完整 OCR、账号、金额、手机号、设备标识和运行日志不公开。`verified` 只根据实际业务终点填写。

测试期间保持设备前台由当前任务独占。用户操作、其他脚本或另一个 AI 同时切换页面时，立即保留当前失败样本；协调设备交还后再恢复。不能把被人工切换的运行记为脚本通过或直接修改坐标来适配。

MCP 的 `watch` 每次最多等待 5 秒，返回 pending 时继续查询，使暂停/停止请求能及时进入服务；CLI watch 可按 seconds 持续等待。每个请求通过 nonce 关联自己的 run_id，不把随后另一任务的状态误当成本次结果。

## 流程分组与普通运行提速（0.3.5）

流程管理按文件夹展开/收起，右滑流程选择“分组”，可新建名称。可选 `group` 字段随脚本部署、导入导出保留；不带字段的旧流程按已有功能块推断“小程序、App 任务、工具、群机器人、未分类”。分组不改变执行步骤、定时或活动流程。读取手机现有脚本后再修改，保留其 group，不用旧预设覆盖个人分类。

已校准的按钮仍使用原有页面规则和坐标；仅在相邻小程序功能块入口复用 0.5 秒内的 OCR。点击、滑动、输入、启动及未知设备命令先使缓存失效；页面跳转等待与结果校验仍取新观察。不要为了提速删掉登录、几何、前台或业务结果验证。

坐标优先执行、真实区域 OCR 和新版验证边界见 [坐标策略](coordinate-workflows.md)。
