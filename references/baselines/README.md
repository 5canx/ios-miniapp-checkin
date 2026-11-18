# 已验证的公开基线

`reuse.py plan current.json --task storm` 会读取同目录下的 `storm.json`。其他任务名为 `asus`、`colorful`、`yogurt`。记录按对应任务、通过的功能块版本和实际界面创建。私有版本与公开样本不同时，优先显式指定 `--baseline 私有已验证记录.json`。没有适用记录时仍先读[现有业务路径](../checkin-workflow.md)，沿已知入口确认当前页面。记录未观察的分支保持待验收。

电脑上生成公开基线的步骤如下：

1. `runner_version` 取实际安装的 autodam 包版本，完整保留版本后缀；`host_version` 取宿主微信的 `CFBundleShortVersionString`（或该包 `get_app_info` 中相应的版本字段）；`ios_version` 取系统产品版本。`mini_version` 取当前小程序公开版本，无法取得时填写 `unavailable`。使用原始版本字符串，避免附加展示名、设备名或内部标识。
2. 从使用的编辑器导出或同版、逐块相同的预设读取单个目标流程。运行下面的校验命令，只取输出的 `blocks_sha256` 作为 `flow_sha256`。算法为对所选流程的 `blocks` 数组以 Python `json.dumps(blocks,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False)` 编码 UTF-8 后计算 SHA-256。步骤顺序、校准参数变化均会改变摘要；名字、定时开关和测试数据不参与。
3. 依照[观察文件示例](../../examples/observation.json) 填真实的 `layout`（逻辑宽高、缩放、方向）与 `pages`。为每个到达的页面选至少两个已核验的稳定语义锚点，使用公共 ID，如 `profile_title` 或 `ledger_heading`。排除账号、分数、本地路径、网络地址、实际日期和截图。公开样本绝不能从演示 observation 推断。
4. 对照私有实机记录，完整路径达到本任务限定的业务目标后，才执行 `record` 写入一个全新文件。华硕个人中心选 `profile_verified`；已有今日回执选 `already_today`；确有本次新动作且读回独立回执才用 `new_receipt`。保留私有历史，发布新基线前复核差异。

```sh
python3 scripts/flow.py validate flow-export.json --id "$FLOW_ID"
python3 scripts/reuse.py record observed.json --verified already_today --out references/baselines/storm.json
python3 scripts/reuse.py plan observed.json --task storm
```

`reuse` 表示已记录页面均与本次观察吻合；`reuse_observed` 仅表示已看到的页面一致，其余 `pending_pages` 在正常执行到达时逐页核对。`check_changed` 列出变化的版本、几何或页面。验证码、账号、隐私、付款和未识别弹窗优先处理，`--gate verification` 等会暂停动作，即使当前页面指纹吻合。
