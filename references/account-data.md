# 账户、奖励与日志

真实结果写在用户控制的私有目录，同步或导出前由用户确定范围。设备日志和截图可能包含未预期的身份或消息信息。截图、屏幕原始 OCR、设备标识与带测试数据的完整流程均不放入公开仓库。

| 字段 | 如何取值 |
|---|---|
| 结果、当地日期与时间 | 任务、时区、观察时间、回执类型。首次发生时间与本次读到的时间分别记录。 |
| 账户 | 经用户授权且实际可见时记录昵称、展示的 ID、会员等级和连续天数；默认报告可脱敏，未展示标“未显示”。 |
| 本次发放 | 记录奖励种类、数额、单位、额外或连续奖励、是否需领取和可见回执。规则页上写的数值仅作为规则。 |
| 前后余额 | 对同一账户、同一币种、同一积分项目分别记签到前后余额；都有来源时计算差额。差额有其他活动干扰时标“归属未知”。 |
| 日志 | 时间、流程和步骤、当前页面、期望/观察锚点、动作、结果、重试次数、异常分类、私有证据路径。数据来源标页面展示、无障碍树、OCR 或人工读屏。 |

运行失败时先记录同一时刻的截图、识别结果、当前步骤和简明错误，再恢复；截图失败时如实记录原因。终态将“业务回执已确认”和“账户字段可读范围”分别写清；无法读到的钱包余额保持未知。示例记录可采用：
```json
{"task":"example","result":"unconfirmed","read_at":null,"timezone":null,"receipt_source":null,"award":null,"points_before":null,"points_after":null,"cash_balance":null,"private_evidence_ref":null}
```

## autodam 的私有记录

在支持结构化记录的版本中，用当前测试或定时运行的存储上下文确定 `evidence_root`。每次运行及同日汇总分别位于：

```text
<evidence_root>/checkin-records/YYYY-MM-DD/<storm|colorful|yogurt>/runs/<marker>.json
<evidence_root>/checkin-records/YYYY-MM-DD/<storm|colorful|yogurt>/receipt.json
<evidence_root>/failures/<marker>/<step>-<uuid>/report.json
<evidence_root>/failures/recent/<scope>.json
```

失败目录内可能有 `screen.jpg`。先读报告中的截图状态和关联证据，敏感页面或无法安全取图会只留元数据。单次运行读 `runs`，同日首次验收与之后的复跑通过 `receipt.json` 关联。华硕的个人中心验收从相应步骤日志获取；不要为它推算一笔签到积分。
