# ios-miniapp-checkin

给 AI 使用的 iPhone 小程序签到 Skill。它能帮助执行者读取已有 autodam 流程，找到已经确认的页面和回执，定位失败的步骤并生成可导入的 JSON。手机端运行编辑器中的功能块，随附 Python 工具运行在电脑上。

## 调用

将此目录作为名为 `ios-miniapp-checkin` 的 Skill 安装到支持 Agent Skills 的宿主。例如，个人 Codex Skill 可放在 `~/.codex/skills/ios-miniapp-checkin/`。一次自然语言调用示例：

> 用 $ios-miniapp-checkin 检查我指定的小程序，复用上次验证过的流程，记录今天的签到结果和可见积分。

只需要写脚本时，可以说“用 $ios-miniapp-checkin 准备可导入的流程，我自己在手机测试”。入口和完整执行顺序见 [SKILL.md](SKILL.md)。

## 试用配套工具

需要 Python 3.8+。在 Skill 根目录运行：

```sh
python3 scripts/flow.py validate examples/normal-checkin.json --id example-read-receipt
python3 scripts/reuse.py plan examples/observation.json
```

- [运行器与部署](references/app-architecture.md) 说明如何只读探测包、配置路径，使用编辑器导入并保护现有流程。
- [业务知识](references/checkin-workflow.md) 描述四个现有小程序的可复用公开页面语义。四条已通过真机验证的流程有对应的[功能块与页面基线](references/baselines/README.md)。每次运行再用当日私有回执确认业务结果。
- [本机流程样例](examples/normal-checkin.json) 是合成页面上的只读演示。发布前另在用户授权的设备上按 [验收用例](references/test-cases.md) 验证真实业务。

完整配置、实机截图、账户信息和运行原始记录存放在仓库外的私有目录。

已授权的 USB MCP 连接可用时，`scripts/deploy.py` 能从系统「文件」的实际 App Group 找到本机的「下载」目录，写入一个新流程文件并校验读回内容，再交由原生编辑器导入。命令及安装版本兼容条件见 [部署说明](references/app-architecture.md)。
