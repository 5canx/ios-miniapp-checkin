# 人工录制一次，AI 学习并验证

复用手机已有 `CNManualRecorder`、页面取样模块和 USB 联动，不新增屏幕录制器、不注入触摸 Hook。当前 native recorder 保存页面变化，不能还原实际手指事件。

## 实际支持范围

| 能力 | 实现与已知边界 |
| --- | --- |
| OCR | 运行器调用已安装 iOS MCP `ocr_screen` / `describe_screen`；不是另一套识别服务 |
| 页面截图、取样 | 既有 capture 与真实 MCP；联动自动回传图像、OCR、AX 和几何 |
| 页面录制 | 原生 recorder，首帧约 5 秒后、后续约 2 秒轮询，实际采样耗时另计；变化帧最多 80，最长 10 分钟 |
| 页面观察时间 | 每帧 `at`；不是手指动作时间，也不能直接当作脚本等待时长 |
| 元素信息 | `ax` 和 `ocr` 的扁平节点，点坐标/归一化矩形；每组最多 64，超过时提供总数；不等于完整父子层级 |
| 实际点击/滑动/触摸时间戳 | 原生录制未提供。`annotations.tap_pt` 是人工补充位置；执行页图的 actions 是脚本请求的动作，两者都不是人工触摸采集 |
| 连续视频 | 此录制模块未提供视频文件，仅变化页预览 |
| 脚本回放和控制 | 已有功能块执行器；联动提供部署、启动、暂停、恢复、停止与实际终态 |
| 日志、结果 | 设备原生 daemon.log、运行状态及业务回执自动下载到私有目录 |

## 操作方式

AI 通过 `recorder start` 开始，确认 `recorder status` 为 recording/ready，再交给用户操作。用户也可以在原生 App 中开始/停止。操作结束后停止录制，AI 调用：

```sh
python3 scripts/link.py learn --args '{"flow_id":"my-learned-flow","name":"录制学习候选","final_keyword":"实际最后一页可见的验收文字"}'
```

`learn` 自动从手机读取录制与预览，调用 `scripts/learn.py`，在电脑私有目录生成：

- `analysis.json`：页面、元素定位候选、登录状态变化、转移、缺失信息和证据来源。
- `navigation.mmd`：按实际观察顺序生成的页面流程图；未知动作明确标记 unknown。
- `flow-candidate.json`：现有标准功能块格式。标注点能唯一对应文字时，生成限区文字定位，不直接重放坐标。
- `learning-notes.md`：复用、恢复及验证规则；保持未验收状态。

原始 recording.json 和预览保留在 recording_fetch 返回的私有目录，analysis 的 preview 对应其中的文件。含密码/验证码的页面不进入分析定位或脚本候选。原始文件可能敏感，不复制进仓库。

缺少触摸事件时，不能自动声称“已完整学习”。AI 先从已有任务、登录知识和基线补齐已验证转移；未知转移根据真实页面提出候选并单条验证。必要时通过已有 annotate 补充位置与意图，不需要用户复制文件。滑动方向、输入内容、弹窗触发条件和等待时长无法从变化帧唯一确定时，留空或标记待确认。

真实测试还观察到 AX/OCR 与转场后的预览可能不一致，尤其是自定义设置分类及微信 WebView。查看预览核对定位文字；不一致时用现有 `sample` 重新观察变化页，不信任旧元素树。录制因 daemon 重启标记 interrupted 时，已保存帧仍可读取和分析，但 candidate_ready_for_device_test 必须为 false。当前单页录制生成与真机验证已通过，多页录制稳定性仍待修复和复验。

## 从候选到可复用流程

1. 读取 analysis 中 missing 和 candidate_ready_for_device_test。缺失转移先补齐，不能跳过后标记完成。
2. 核对首个页面、几何、每个定位条件与最终业务断言。最终文字必须真的出现在最后一帧；单纯“点击完成”不是签到证据。
3. 复用 `flow.py validate`，用 `link deploy` 携带旧 revision 部署，run/watch 回传真实结果。失败只修变化步骤。
4. 只有真机执行及业务结果都通过后，才更新任务基线和登录规则。候选生成本身一直标记 device_tested=false、business_verified=false。
5. 已有经验优先复用。仅首次、页面变化或异常时完整取样；微信 WebView 的 AX 已观察到滞后，不能为了减少 OCR 而盲信旧树。

公开同步只摘录通用语义、步骤、异常条件和验收范围；不自动发布原始 OCR、截图、账号、金额或录制文件。现有 `recordings/` 忽略规则保持生效，无需在 Skill 中另建一个公开的个人录制库。
