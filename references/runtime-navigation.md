# AutoDam：运行性能与页面状态

0.4.2 最新影视飓风结果与组合导航规则见 [快速流程与悬浮球](storm-fast-0.4.2.md)。下文 0.3.20 性能数字保留作历史对照；最新组合导航将输入回读并入结果卡检查，独立 mini_nav 块仍保留原契约。

运行固定任务先用 `link.py read` 取得现有流程，复用 `open_mini` 或四个 `mini_nav`。不要在 Skill 外再包一套搜索/返回循环。AutoDam 的 `CNWechatPageState` 和 `navigateTo` 按当前页面选择已验证的下一条边。导航状态包括 HOME、CONTACTS、DISCOVER、ME、HOST_TAB、SEARCH、MINI_SEARCH、SEARCH_OTHER、RESULTS、TARGET_MINI、ACTIVITY、OTHER_MINI、CHAT、POPUP、AUTH_REQUIRED、UNKNOWN。

- 已在可复用目标入口，或影视飓风签到日历：保留现场，跳过搜索。安慕希/七彩虹其他业务子页沿用原来的安全关闭和重进逻辑，本轮没有扩展它们的返回图。需要个人中心的业务块使用日历→个人中心的已验证返回边，不关闭再搜索。
- 通讯录/发现/我的→微信标签→搜索→小程序分类。当前为目标搜索结果时复用查询，不重新输入。
- 聊天页只有在 AX 确认返回与输入栏后才能返回。“可按住转文字”变体需要同时确认底部对应控件、语音及表情，不能仅凭一条提示点击返回；未知页没有安全边就停，不按固定次数返回。
- 每条边只发送一次手势，随后在有界时间内检查后置状态。无变化、路径循环或认证关口即停。隐私协议沿用现有暂停规则。
- 微信搜索横向展开时文字已可读，按钮却仍在移动。分类入口必须落到校准位置后才可点，不能仅凭“看到了小程序”判断就绪。
- 原生 AX 树可能同时包含搜索页和被遮挡的消息列表，不能以底栏仍存在判断为 HOME。OCR 状态优先看搜索层，AX 只辅助具名控件定位。

## 调用与缓存

稳定操作继续固定坐标；搜索过渡只 OCR 顶部/分类区域，输入只 OCR 搜索框，结果只 OCR 完整名称、类型及官方卡片区域。进入小程序后仍验证身份，签到仍验证当天状态或真实奖励。没有在每次点击后追加截图、取样或 AI 调用。设备目前无通用图色匹配工具，不能编造接口。

OCR 观察仅复用 1 秒内且没有设备操作的结果。完整页面可满足局部读取；局部结果仅复用于完全相同的裁剪区域，不冒充全屏结果。私有样本中保存 `observation_scope`、`observation_region`（屏幕点）和 `recognition`，页面指纹包含取样范围，不能把头部小样本当作整页知识。点击、输入、按键等操作开始前失效，包括传输失败的不确定操作。不同页面、不同范围或超时都重新读取。

UI 操作有前后依赖，保持串行；当前 OCR worker 本身串行。不要同时发手势或并行 OCR 来“提速”。日志分析可以离线进行。

个人中心返回会保留滚动偏移。账户字段不在可视区时，走已测向上恢复路径，而非重复 OCR 同一页。积分、余额按各自唯一文字标签上方的数值读取，容忍回弹偏移；同名标签多于一个、字段不在范围或数值不合法时留空。

## OCR 核实

实机 `ocr_screen.recognition` 与模型目录共同确认：**PP-OCRv5_mobile_det + PP-OCRv5_mobile_rec，ONNX Runtime 1.20.1，CPUExecutionProvider，本机运行**。这是传统检测＋识别模型，不是 PaddleOCR-VL，也不调用远程模型 API。模型逻辑目录 `/usr/share/ios-mcp/paddleocr/`，包含 `det.onnx`、`rec.onnx`、`dictionary.json`、`det.yml`、`rec.yml`、`sha256.json`；实际 RootHide 前缀由设备解析，勿硬编码设备路径。

源码与实机元数据见 [原生推理实现](https://github.com/witchan/ios-mcp/blob/main/mcp-ocr-worker/PaddleOCR.mm)、[worker 生命周期](https://github.com/witchan/ios-mcp/blob/main/mcp-ocr-worker/main.mm)、[管理器](https://github.com/witchan/ios-mcp/blob/main/PaddleOCRManager.m)。worker 存活时复用会话，闲置约 60 秒退出后下一次重新加载；连续两次区域请求实测约 0.470 / 0.437 秒，worker PID 相同；没有正常每一步重载的证据。源码还有每请求校验模型文件、截图编码/解码与全屏文字逐行识别开销，本轮未修改上游 worker，未单独测量这些开销的占比。

当前已使用 Mobile 模型，先减少全屏识别、裁剪和缓存，不升级为 OCR-VL。Vision 测试在此机超时，未切换引擎。微信首页的一次实测：全屏 PaddleOCR 2.54 秒、顶部 130pt 区域 0.44 秒；AX 0.19 秒但存在被遮挡节点，不可当作全面准确性指标。

## 本轮验收

见私有运行目录 `~/Library/Application Support/autodam-link/diagnostics/0.3.20` 和 `runs`；不要上传原始文件。0.3.19 首页启动的 16 步基线为 58.779 秒、21 次 OCR、OCR 34.733 秒。0.3.20 同流程最终回归 39.286 秒、17 次 OCR、OCR 23.256 秒；约减少 33.2% 总耗时。结果为当天已签到，读到当前积分与账户余额；不证明本轮新增奖励。单机有限样本，不能外推全 App OCR 准确率。

生成器和 ActivitySkill 继续复用原生导航，运行器升级后新建候选并重新校准、验证；不要直接改写旧稳定版本的证明。

本轮还验证了 HOME、CONTACTS、SEARCH、CHAT（可按住转文字）、ACTIVITY 五种真机起点；未登记设置页 UNKNOWN 按预期安全停止。活动页复用仅 1 次 OCR、没有触控或输入。POPUP/登录挑战未人为触发，不宣称已完成这类真机回归。ActivitySkill 新候选的真机 verify 与独立 CLI replay 均通过，当前积分/余额读到，旧稳定版保留；原始证据在 `~/Library/Application Support/ActivitySkill/bridge/runs`。

## 2026-11-19 补充：内置与外部引擎须区分

正常任务通过 MCP 使用 PP-OCRv5 Mobile / ORT；不是 AutoDam 本体已链接 PaddlePaddle。AutoDam 另有 Apple Vision 失败截图脱敏代码，不代表任务正常走 Vision。AutoGo 现有 SDK 原生库使用 NCNN 和内嵌 V5 Mobile；本地 Go 代码是桩，不能拿 nil 返回的耗时当真机测试。

同一真实 428×926 图像、5 次组件测试（后 4 次中位数）：NCNN 原生调用全屏约 451ms、顶部区域 19ms；已安装 ONNX worker 回路约 1787ms / 184ms。NCNN 不含采集、Go/CGo 包装，worker 包含 IPC/解码，且预处理不同，不能把倍数说成“只要内置就能提升这么多”。小样本公共可见锚点均匹配，不等于已验证积分金额识别率。

worker 已复用模型，正常热请求不反复初始化；每次模型校验约 9ms，不是主要瓶颈。Paddle 的 fast 参数不会换一套模型。现有 AutoGo 帮助函数却每次 New/Close，Best 还跑两套模型，不要盲目复制这部分。

独立原生截屏未通过，USB screenshotr 未开启；不要编造原始帧接口。独立进程 Vision 默认和 CPU-only 请求也失败，根因待定位，不默认切换。若开发本地后端，应先复用已允许的采集来源，验证真实小字/数字和坐标映射，独立后台 worker 保留原后端回退。此轮未替换生产引擎，不宣称已完成整流程加速。
