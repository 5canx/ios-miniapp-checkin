---
name: ios-miniapp-checkin
description: 在已授权的 iPhone 上用 autodam 和 iOS MCP 编辑、迁移、执行或排查小程序签到流程。适用于微信小程序导航、弹窗与授权、按日幂等签到、积分流水验收、账户字段采集，以及通过 USB 控制服务开发、部署、运行、回传和修复手机脚本；优先复用经过实机确认的页面指纹和现有脚本。
---

# iOS 小程序签到

## 先找已有流程

用户提供新录制或要求“操作一次让 AI 学习”时，先读 [录制学习工作流](references/recording-learning.md)，调用 `link.py learn` 自动取得原生录制、分析页面与生成标准功能块候选。真实触摸、滑动与触摸时间戳在当前录制中不可用，不能把页面变化推断成已记录动作。已有登录先读 [登录经验](references/login-workflow.md)，只重新采样变化页。

已有执行和录制的文件映射见 [页面经验与样本索引](references/page-samples.md)。优先读取这些私有证据和对应基线，不另建重复页面库。

1. 确认用户本次要做的事、目标小程序和动作范围。只要求写脚本或自行测试时，在本机完成准备。需要真实运行时，记录设备当地日期、时区、屏幕方向、逻辑尺寸和缩放。
2. 先读 [USB 联动与自主开发](references/control-link.md)，用 `scripts/link.py discover` 核对真实安装，再用 `read` 取得设备当前流程及版本。读取 [运行器与部署](references/app-architecture.md)、[业务路径与回执](references/checkin-workflow.md)、[已验证基线索引](references/baselines/README.md) 及目标流程。先查同任务私有已验证记录，其次读随 Skill 发布的任务基线。优先通过控制服务读取当前流程；旧版设备才用编辑器导出，包内预设是备选。先看旧版本、校准区域、步骤顺序、最后一次实机回执和失败位置。把截图、录屏和完整导出留在用户自己的目录。
3. 在已授权连接中，检查只读工具清单、设备响应和前台页面。前台 bundle、界面树与当前截图矛盾时先消除矛盾；以输入、点击作为探活会影响页面。[页面识别](references/page-navigation.md)
4. 取得包版本及宿主版本，用 `scripts/flow.py validate` 计算功能块摘要。按 [指纹样例](examples/observation.json) 填写稳定语义锚点 ID，去掉昵称、金额、日期等可变文本。按下面的命令判断此次需复查的位置。没有基线时，先读已有业务路径并确认首个页面。基线吻合时沿原流程执行，逐一核对运行中遇到的页面。页面指纹变化时重新采样该页及其直接后置页面；包或运行器升级时核查执行能力和入口；旋转、缩放变化时复核坐标。把已获实机回执的完整新记录写为一版新基线。

```sh
python3 scripts/flow.py validate flow-export.json --id FLOW_ID
python3 scripts/reuse.py plan observed.json --task storm
python3 scripts/reuse.py plan observed.json --baseline last-verified.json
```

有未到达的已知页面时，工具返回 `reuse_observed` 并列出 `pending_pages`；每到一页重新核对。验证码或权限层出现时用 `--gate verification` 或 `--gate privacy` 等声明当前关口，优先暂停至用户处理。

## 执行与验收

- 连接服务只在实际调用设备工具时探活。通过 `tool_schema` 获取设备真实 UI 工具参数，用 `sample` 取当前页，复用已有页面图和定位规则。新增需求依次完成读取旧经验、取缺失样本、修改标准功能块、带版本部署、运行、回传证据、修复和回归，详见联动说明。
- 先到小程序右下角“我的”核对登录，分别记录 logged_in、logged_out、unconfirmed。用户已有登录授权可处理已明确的一键登录；短信验证码由用户处理。不要以看不到登录按钮推断已登录。
- 定位优先级：已验证流程与绑定页面、分辨率、方向、显示缩放的固定坐标优先；正常点击不重新 OCR、抓树或截图。必要的入口/登录/业务结果检查保留；积分、余额、账户等动态数据优先限区读取。只有未知页面、元素不存在、弹窗、跳转失败或结果异常时才重新识别。详见 [坐标知识库与快速执行](references/coordinate-workflows.md)。
- 一次只跑一条微信流程，检查结果后再决定下一条。微信异常恢复页、失去登录或系统反复重启时立即停止测试，保留现场并等用户恢复；不自动清理缓存、退出账号或连续拉起微信。

- 从真实入口打开已确认的宿主。依次定位宿主首页、进入小程序搜索、输入并回读完整名称、打开匹配项、核验小程序身份。GUI 与日志保留独立功能块；普通运行复用执行时必要的 OCR，不在每个功能块后追加完整取样。[小程序导航](references/miniapp-switching.md)
- 沿已验证路径直接执行坐标和已测等待。已知关闭、返回、登录选择复用记录；未知弹窗和前台被切走时停止动作并取样，复核后更新该段规则。退出前保存业务回执，退出后确认返回层级。[弹窗与关闭](references/popup-handling.md) · [权限与登录](references/permission-handling.md)
- 用户只要求查询或核对积分时，将目标页人工或按已授权路径打开，使用 `--observe-only` 校验、准备或投放只读流程。只读流程仅查当前页面，缺少今日记录也停在查询结果。用户授权签到时，先读今日状态，再决定是否签到。只在已确认的“未签到”页执行一次，等待业务回执。已签到时读取当天状态；点击结果不明确时进入只读复核。按目标区分“个人中心已进入”“本次新增签到”“当天已签”“证据不足”“等待用户处理”。[业务路径与回执](references/checkin-workflow.md)
- 对照页面记录实际可读的奖励、积分、余额和其他相关状态。每项注明取值来源与当地时间；无法读到的字段留空并说明。按 [账户与日志](references/account-data.md) 保存本地资料。遇到断线、未知页或未确认的副作用时用 [恢复表](references/error-handling.md)。
- 对新增或修复流程，从宿主真实入口到业务回执及按需退出走一次，再同日重跑验证幂等。用户已在当天手工完成时，只能证明“已签到”分支；区分静态检查、脚本回归、真机执行结果。[验收用例](references/test-cases.md)

## 保存、导入与下次调用

把经过验证的步骤、限区定位和验收规则保存在设备当前流程中。用 `scripts/link.py deploy` 直接部署，检查新版本和自动备份回读，再用 `run`、`watch` 完成真机运行及证据回传。原生编辑器会读到同一份流程。版本冲突先合并，结果不确定不重复启动。设备不支持控制协议时才使用旧 `flow.py prepare` 和 `deploy.py` 的下载导入途径，并明确这是人工兼容路径。正式验收后按用户要求开启定时。

未经实际出现的首次协议页、首次发奖页或系统授权页，标记待采样；不为凑齐样本重置用户账号与授权。页面库和完整日志保存在设备及电脑私有目录。公开同步前从样本提取通用定位规则，去除个人字段；不要直接复制私有样本库进 Git。
```sh
python3 scripts/flow.py prepare flow-export.json --id FLOW_ID --out checked-flow.json
python3 scripts/reuse.py record observed.json --verified already_today --out next-baseline.json
```

`--verified` 由读取真实回执的操作者填写。可选值包括 `already_today`、`new_receipt`、`profile_verified`。下次调用先读此记录及对应版本的业务路径。公开改动仅包含通用控件语义、示例和无账号信息的定位规则。

## 可运行示例

在 Skill 根目录运行下面的命令，从演示导出生成一个只读验收流程。它包含两个屏幕验证块，适合检查工具链和 JSON 导入。

```sh
python3 scripts/flow.py validate examples/normal-checkin.json --id example-read-receipt
python3 scripts/reuse.py plan examples/observation.json
```

结合 [弹窗示例](examples/popup-handling.md) 与 [断线示例](examples/recovery.md) 检查恢复分支。
