# 运行器与部署

有 control protocol 1 的 autodam，优先使用 [USB 联动控制服务](control-link.md) 直接读取、带版本部署、启动和回传。本页的文件导入是旧安装版兼容路径。新功能通过真实 `--bridge-info` 检测，不根据名字推测。

## 确认安装与连接

在电脑验证已有授权通道可读。已授权 USB 配对可用时，用本机已安装的设备管理工具检查“已连接并配对”；SSH 走用户已经配置的主机别名和主机密钥。发现多个设备时按用户指定的那台继续。同一台设备上的 MCP 连接还要核对工具列表，并用只读屏幕调用确认本次会话实际可响应。线缆、SSH、MCP 各自有独立连接状态。根据用户授权选择其一，无需为发现目录安装软件。

在已经获准的设备 shell 运行 `sh discover.sh`。若从电脑使用已有 SSH 别名，可将探测器从标准输入传给远端 shell（别名由用户提供）：

```sh
ssh -o BatchMode=yes -o ConnectTimeout=8 "$DEVICE_ALIAS" sh -s < scripts/discover.sh
```

只有本机文件系统副本时，运行 `sh scripts/discover.sh "$MOUNTED_IOS_ROOT"`。探测器首先查询设备上已安装且名称匹配的 Debian 包和包文件清单，再检查实际存在的应用、daemon、启动项、基础配置与移动用户偏好。存在 Python 或兼容 plutil 时读取状态目录及配置键，不输出整份配置。离线副本须提供可读的实际目录，例如独立挂载的越狱前缀；缺失挂载、隐式 root 映射、权限不足或使用不同命名的构建均可造成未发现。用包管理器安装清单和运行器源码确认空缺，避免把“未发现”当作“未安装”。

## 定位真实存储

| 探测结果 | 核对方式与用途 |
|---|---|
| `package`、`mcp_package`、`app_bundle` | 读包名和安装版本；用 App 的 Info.plist 对照显示名、bundle 与版本。不同 fork 应检查各自导入实现。 |
| `launchd`、`daemon`、`base_config` | 检查服务实际指向的可执行文件、运行用户、配置路径参数；自定义启动配置以参数为准。 |
| `confirmed_flow_preferences` | 已解析偏好键 `configuration_json` 并确认包含 `flows`。每个流程的有序可执行步骤在 `blocks`。 |
| `configuration_key_present`、`preferences_candidate` | 分别代表键已存在、仅发现文件。优先编辑器导出核对一个已有流程的 ID 与步骤。 |
| `state_directory`、`configured_state_directory` | 前者路径已存在，后者仅在基础配置中读到。检查实际目录中当前运行的日志和状态文件。 |

当前 autodam 适配的格式为 `com.witchan.mcpflow.flows`、版本 `1`。导出物是含 `flows` 的 JSON，程序从编辑器保存的配置执行，不需另造脚本目录。支持的原生步骤、区域名与工具以设备安装版和工具列表为准。功能块校准区域用同一当前方向的 `[left,top,right,bottom]`，归一化到 0..1。某些坐标点击块另带录制参考宽高；这两种表示各用各的字段。

## 导入一份已验证的流程

1. 在流程管理中导出目标流程到本地私有目录，记下当前活动流程、原 ID、名称、间隔及启用状态。也可从已确认同版本项目的 `App/Resources` 读取预设。实机校准优先使用编辑器导出版本。
2. 在电脑运行 `python3 scripts/flow.py validate SOURCE.json --id FLOW_ID`，保留功能块摘要。预检会递归检查已知块类型、循环规模、区域和验收块；设备内置任务名、区域白名单、MCP 工具参数及实际页面仍以安装版为准。
3. 如目标流程和现有流程摘要一致，比较本次需要的测试数据与运行间隔，合适时直接选用现有流程。需要导入时运行 `python3 scripts/flow.py prepare SOURCE.json --id FLOW_ID --out NEW.json`。工具仅提取所选流程的步骤、ID、名称、测试数据与间隔，拒绝覆盖已存在的输出文件。测试数据与块文本可能含私有值，产物按私有文件管理。
4. 通过用户可用的文件传输把产物放入 iOS「文件」可读的位置，或使用编辑器支持的粘贴导入。经「流程管理 → 导入 → 从 JSON 文件导入」选择产物。此版导入立即保存独立副本：原有流程继续保留，同名会加后缀，ID 冲突会生成新的 ID，新副本默认停用定时。
5. 重新打开流程管理，核对导入的名称、顺序、测试数据、间隔；用新 ID 手动测试一次并核对结果。按用户要求设置定时。现有生产流程仍在运行时先核对其定时，按用户意图完成新旧切换，避免两个副本同时运行。保留此前导出以便回看。只将文件复制到系统目录不能代替导入保存。

如安装版本没有对应块，先确认兼容版本或用其已有功能块重建。上游对应检查位置为当前 fork 的 `Sources/CNFlowTransfer.m`、`Sources/CNConfig.m`、`Sources/main.m` 与 `App/CNEditor.m`。

## 通过已授权 USB 直接投放到「下载」

复用已经连接正确设备的 USB 端口转发，设置 `LOCAL_MCP` 为该转发的本机回环地址和 `/mcp` 路径。按手头导出选择 `FLOW_ID`。脚本首先确认 autodam 已安装，从「文件」App 的 `get_app_info` 读取 `group_containers["group.com.apple.FileProvider.LocalStorage"]`，再逐级检查 `File Provider Storage/Downloads` 确为目录。容器 UUID 每次动态查询。无需读取相册、联系人、现有下载文件内容或偏好数据库。

```sh
python3 scripts/deploy.py flow-export.json --id "$FLOW_ID" --mcp-url "$LOCAL_MCP"
python3 scripts/deploy.py flow-export.json --id "$FLOW_ID" --mcp-url "$LOCAL_MCP" --write
```

第一条只读探测，第二条将所选流程写为全新的 `checkin-flow-随机标识.json` 并读回这一份文件逐字节校验。记下第二条返回的文件名，在「流程管理 → 导入 → 从 JSON 文件导入 → 在我的 iPhone 上 → 下载」选它，然后重新打开已保存的流程。若用户只要核对当日积分，应在 validate、prepare、deploy 命令加 `--observe-only`，该选项拒绝 tap、滚动、导航、内置业务动作与通用工具，只允许当前页的 verify、无动作 find、wait 和这些只读块的有界循环。例如 `python3 scripts/flow.py validate examples/normal-checkin.json --id example-read-receipt --observe-only`。通用 verify 只用于验页面或独立状态词。要判定积分入账，在真实积分明细页逐条只读复核同一笔的日期、签到标题和正积分；两个关键词各自命中不能证明同一笔。无回执时保留未确认状态。若同版流程已在编辑器内无需再导入。传输中断时先按已输出的文件名核对，避免反复导入副本。连接断开、目录缺失、手机锁屏、写入权限不足或读回不一致均应先处理具体原因；也可走原生文件选择器。若 fork 使用不同编辑器 bundle，用 `--editor-bundle` 指定已确认的标识。当前下载适配依据为 iOS MCP 的 [AppManager](https://github.com/witchan/ios-mcp/blob/main/AppManager.m)、[文件工具](https://github.com/witchan/ios-mcp/blob/main/FileSystemManager.m) 和 [工具注册](https://github.com/witchan/ios-mcp/blob/main/MCPServer.m)。
