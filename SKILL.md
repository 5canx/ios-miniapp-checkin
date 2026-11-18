---
name: ios-miniapp-checkin
description: 在已授权的 iPhone 上用 autodam 和 iOS MCP 编辑、迁移、执行或排查小程序签到流程。适用于微信小程序导航、弹窗与授权、按日幂等签到、积分流水验收、账户字段采集，以及把已校准流程导入设备；优先复用经过实机确认的页面指纹和现有脚本。
---

# iOS 小程序签到

## 先找已有流程

1. 确认用户本次要做的事、目标小程序和动作范围。只要求写脚本或自行测试时，在本机完成准备。需要真实运行时，记录设备当地日期、时区、屏幕方向、逻辑尺寸和缩放。
2. 读取 [运行器与部署](references/app-architecture.md)、[业务路径与回执](references/checkin-workflow.md)、[已验证基线索引](references/baselines/README.md) 及目标流程。先查同任务私有已验证记录，其次读随 Skill 发布的任务基线。优先用编辑器导出当前流程；包内预设是备选。先看旧版本、校准区域、步骤顺序、最后一次实机回执和失败位置。把截图、录屏和完整导出留在用户自己的目录。
3. 在已授权连接中，检查只读工具清单、设备响应和前台页面。前台 bundle、界面树与当前截图矛盾时先消除矛盾；以输入、点击作为探活会影响页面。[页面识别](references/page-navigation.md)
4. 取得包版本及宿主版本，用 `scripts/flow.py validate` 计算功能块摘要。按 [指纹样例](examples/observation.json) 填写稳定语义锚点 ID，去掉昵称、金额、日期等可变文本。按下面的命令判断此次需复查的位置。没有基线时，先读已有业务路径并确认首个页面。基线吻合时沿原流程执行，逐一核对运行中遇到的页面。页面指纹变化时重新采样该页及其直接后置页面；包或运行器升级时核查执行能力和入口；旋转、缩放变化时复核坐标。把已获实机回执的完整新记录写为一版新基线。

```sh
python3 scripts/flow.py validate flow-export.json --id FLOW_ID
python3 scripts/reuse.py plan observed.json --task storm
python3 scripts/reuse.py plan observed.json --baseline last-verified.json
```

有未到达的已知页面时，工具返回 `reuse_observed` 并列出 `pending_pages`；每到一页重新核对。验证码或权限层出现时用 `--gate verification` 或 `--gate privacy` 等声明当前关口，优先暂停至用户处理。

## 执行与验收

- 从真实入口打开已确认的宿主。依次定位宿主首页、进入小程序搜索、输入并回读完整名称、打开匹配项、核验小程序身份。每步重新取样，GUI 与日志都保留独立功能块。[小程序导航](references/miniapp-switching.md)
- 每次点击前确认前台、页面身份、遮挡和目标文字。优先采用无障碍元素，其次限区 OCR。按当前场景区分活动遮罩、系统权限、奖励领取和小程序胶囊。退出之前保存回执，退出之后确认返回层级。[弹窗与关闭](references/popup-handling.md) · [权限与登录](references/permission-handling.md)
- 用户只要求查询或核对积分时，将目标页人工或按已授权路径打开，使用 `--observe-only` 校验、准备或投放只读流程。只读流程仅查当前页面，缺少今日记录也停在查询结果。用户授权签到时，先读今日状态，再决定是否签到。只在已确认的“未签到”页执行一次，等待业务回执。已签到时读取当天状态；点击结果不明确时进入只读复核。按目标区分“个人中心已进入”“本次新增签到”“当天已签”“证据不足”“等待用户处理”。[业务路径与回执](references/checkin-workflow.md)
- 对照页面记录实际可读的奖励、积分、余额和其他相关状态。每项注明取值来源与当地时间；无法读到的字段留空并说明。按 [账户与日志](references/account-data.md) 保存本地资料。遇到断线、未知页或未确认的副作用时用 [恢复表](references/error-handling.md)。
- 对新增或修复流程，从宿主真实入口到业务回执及按需退出走一次，再同日重跑验证幂等。用户已在当天手工完成时，只能证明“已签到”分支；区分静态检查、脚本回归、真机执行结果。[验收用例](references/test-cases.md)

## 保存、导入与下次调用

把经过验证的步骤、限区定位和验收规则保存在源流程中。用 `scripts/flow.py prepare` 提取单个已有流程，通过已授权 USB 连接运行 `scripts/deploy.py` 投放到系统「下载」，按 [部署说明](references/app-architecture.md) 在原生编辑器导入并保存；已有同版流程直接复用。导入后核对名称、步骤、编辑器所选流程及定时间隔，正式验收后再按用户要求启用。将旧基线和当前失败证据保留在私有目录。

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
