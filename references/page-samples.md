# 页面经验与私有样本索引

不在 GitHub 存放个人页面库。设备根目录从 `discover` 的 state_directory 取得，电脑根目录由联动返回的 local_directory 指定。

| 资料 | 实际位置/入口 | 复用方式 |
| --- | --- | --- |
| 当前手机流程与版本 | `link read`；私有 scripts/FLOW_ID.json | 修改真实 blocks，部署携带 revision |
| 一次执行的页面库 | `fetch` 返回目录下 page-NNN/page.json、screen.jpg | 页面名称、OCR、AX、几何、block 和 capture_stable；不稳定页需重新核对 |
| 执行导航图 | 同一运行 pages.json | 节点及含脚本请求动作的有向 edges；不是物理触摸日志 |
| 登录检查 | 同一运行 login.json | logged_in、logged_out、unconfirmed 与证据；先复用有效会话 |
| 业务回执 | 同一运行 receipt-TASK.json | outcome、带来源的字段与缺失原因；不能用执行 succeeded 替代业务回执 |
| 原生录制与预览 | `recording_fetch` 或 `learn` 返回的 recording_directory | recording.json、autodam-frame-NNN.jpg；仅真实观察帧 |
| 录制分析 | `learn` 返回的 local_directory | analysis.json、navigation.mmd、flow-candidate.json、learning-notes.md |
| 公开通用页面经验 | [基线索引](baselines/README.md) | 只保存语义锚点、几何、版本和流程摘要 |

当前影视飓风的已验证路径：微信首页 → 小程序搜索 → 完整查询结果 → 商店首页 → 我的/个人中心及已登录标记 → 日历签到入口 → 今日已签日历 → 返回个人中心 → 胶囊关闭 → 微信搜索层。本轮自动保存 19 帧、20 条执行转移；同页的不同观察可能各有一帧，不等同于 19 个不同业务页面。

华硕已验证登录路径见 [登录经验](login-workflow.md)。未出现的首次奖励、授权或其他账号页面不伪造样本，也不重置账号来补齐。私有历史优先于公开基线；版本或锚点变化时仅采样变化页及相邻转移。
