# N16R8 智慧安心节能小屋代理协作说明

本目录是小学组智慧生活作品 `N16R8 智慧安心节能小屋`。后续任何代理或开发者进入本目录时，必须先读：

1. `设计方案.md`
2. `开发文档.md`
3. `assets/n16r8-hk2-wiring-diagram.png`

本项目当前不是通用智能家居模板，而是小学组任务作品：`数据采集`、`智能控制`、`语音交互`、`节能响应` 四条任务必须始终可讲清、可演示、可对应真实硬件。

## 项目身份

| 项 | 值 |
| --- | --- |
| 项目名称 | N16R8 智慧安心节能小屋 |
| 赛项组别 | 小学组智慧生活 |
| project | `smartlife-primary-hk2` |
| profileId | `smartlife-primary-safe-energy-home-v1` |
| 串口波特率 | `115200` |
| 首选路线 | 第一阶段本地 Dashboard + Web Serial；验证后再接 WSS Relay + MQTT |
| MQTT topic 前缀 | `smartlife/primary/hk2/n16r8` |
| GitHub 仓库 | `https://github.com/lostmyukii/zhihuishenghuoxiao2.git` |

## GitHub 同步要求

用户要求“每一步更新 GitHub”。本项目后续开发必须按小步提交执行：

1. 每开始一个可验证步骤前，先确认 `git status --short --branch`。
2. 每完成一个步骤，立即只提交本步骤相关文件，并推送到 `origin/main`。
3. 每次提交信息要说明本步完成了什么，例如 `Update development workflow docs`、`Add firmware protocol skeleton`。
4. 如果本地有不属于当前步骤的改动，不要顺手提交；先确认这些改动是否属于本步骤。
5. 如果 `git push` 失败，停止继续开发，先处理同步问题，避免本地和 GitHub 状态分叉。
6. 不要把 API key、MQTT 密码、Wi-Fi 密码、服务器密码写入提交。

推荐每一步使用：

```bash
git status --short --branch
git add <本步骤文件>
git commit -m "<本步骤说明>"
git push origin main
```

## 不要偏离的设计主线

- 评委必须能看到：生活问题、实体模块、OLED、网页状态同步。
- 真实板必须输出 `hello/telemetry/health/ack` 类 JSON，不用静态占位数据冒充在线。
- 同一套命令要被网页按钮、语音意图和文本快捷命令复用。
- 小学组重点是四项任务闭环，不是越多模块越好。
- MQ-2、水滴、火焰和 PIR 已纳入正式安全感知范围，不再作为可删减扩展。
- MQTT 和可视化是展示增强，必须服务于真实硬件状态。

## 硬件合同

图形示意见 `assets/n16r8-hk2-wiring-diagram.png`。精确连接以此表为准。

| 模块 | GPIO/interface | Demo role |
| --- | --- | --- |
| Light 光敏 | `GPIO1 / ADC1` | 数据采集、光暗开灯、节能判断 |
| MQ-2 AO | `GPIO2 / ADC2` | 厨房烟雾/燃气风险 |
| Sound 声音 | `GPIO4 / ADC4` | 学习噪声提醒 |
| PIR | `GPIO5 / D5` | 有人/无人、离家入侵 |
| Flame 火焰模拟 | `GPIO11` 信号口 | `DO/SIG` 低电平触发，不用明火 |
| Water 水滴 | `GPIO8 / D8` | 漏水提醒 |
| Buzzer 蜂鸣器 | `GPIO13 / D13` | 短提醒与报警 |
| DHT | `GPIO14 / D14` | 温湿度舒适判断 |
| OLED | `SDA=GPIO41, SCL=GPIO42` | 本地数据显示 |
| Relay/Lamp | `GPIO12 / D12` | 低压学习灯 |

重要：命名和 GPIO 不得在 `设计方案.md`、`开发文档.md`、固件、Dashboard、图片说明之间漂移。

本作品确认不使用 8 键 AD、风扇、舵机和 RGB 灯环。模式与阈值由 Dashboard、语音意图和文本快捷命令完成，不得在后续固件、图片或讲稿中重新加入这些模块。

## 安全合同

这些规则是验收合同，不是 UI 偏好：

- 不接 `220V`，继电器只接低压演示灯或指示灯。
- MQ-2 若使用 `5V` 供电，`AO` 必须限压到 `0~3.3V`。
- 所有外部执行器必须共地。
- 上电默认继电器关、蜂鸣器静音；安全告警功能默认保持启用。
- MQ-2 超阈值、水滴触发、火焰触发必须产生安全告警。
- `away` 模式下 PIR 触发必须产生入侵告警。
- 安全告警时，如果 `buzzerEnabled=true`，蜂鸣器应响。
- 厨房风险应在 `buzzerEnabled=true` 时触发蜂鸣器，并让 OLED 与网页明确显示风险来源。
- `actuator.buzzer=false` 只停止手动/测试蜂鸣，不关闭安全报警。
- `set.buzzerEnabled=false` 才是明确安全静音，OLED 和网页必须显示 muted。

## 串口 JSON 协议

串口为 `115200`，每行一个 JSON。不要混入调试文本。

启动：

```json
{"type":"hello","project":"smartlife-primary-hk2","board":"n16r8_esp32s3","profileId":"smartlife-primary-safe-energy-home-v1","baud":115200}
```

遥测：

```json
{"type":"telemetry","mode":"study","sensors":{},"actuators":{},"alerts":[],"energy":{},"health":{}}
```

命令：

```json
{"type":"command","mode":"study"}
{"type":"command","set":{"lightThreshold":35}}
{"type":"command","set":{"buzzerEnabled":false}}
{"type":"voiceIntent","intent":"querySafety"}
```

响应：

```json
{"type":"ack","ok":true,"message":"mode=study"}
```

在线状态只能来自新鲜 `hello` 或 `telemetry`。Dashboard 不得因为本地 demo 初始值而显示开发板在线。

## MQTT / WSS

topic 前缀：

```text
smartlife/primary/hk2/n16r8
```

标准 topic：

```text
smartlife/primary/hk2/n16r8/hello
smartlife/primary/hk2/n16r8/telemetry
smartlife/primary/hk2/n16r8/event
smartlife/primary/hk2/n16r8/health
smartlife/primary/hk2/n16r8/command
smartlife/primary/hk2/n16r8/config
smartlife/primary/hk2/n16r8/voiceIntent
```

首选公网路线：

```text
N16R8 USB -> HTTPS Dashboard Web Serial -> WSS Cloud Relay -> MQTT Broker -> other browsers
```

说明：

- 插板电脑的 Chrome/Edge 页面是 USB 网关，页面必须保持打开。
- Safari/iPhone 可看远程状态，但不要作为 USB 直连网关。
- 如需后台常驻，再用 Python gateway。
- 后续 Wi-Fi/MQTT 固件是第二阶段，不要第一版依赖现场 Wi-Fi。

## Dashboard 要求

- 首屏是实时操作台，不是介绍页。
- 顶部显示开发板、USB、语音状态；第一阶段 WSS、MQTT 明确显示“未配置”。
- 显示四个模式：`home`、`study`、`away`、`energy`。
- 显示传感器：light、sound、temperature、humidity、pir、mq2、water、flame。
- 显示执行器：lamp、buzzer，并同步 OLED 显示内容。
- 显示小屋热区：学习区、厨卫安全区、玄关安防区、中控区。
- 显示日志：`hello`、`telemetry`、`ack`、`event`。
- 断开 USB 后必须显示离线或重连中。
- 语音失败时必须保留文本测试和快捷按钮。

## 实现顺序

1. 冻结硬件和协议合同。
2. 固件实现最小闭环：`hello`、`telemetry`、`ack`、光照、DHT、PIR、学习灯、蜂鸣器。
3. 完成正式安全模块：MQ-2、水滴、火焰及 OLED/网页告警说明。
4. 完成本地 Dashboard、Web Serial 与 mock board 验证。
5. 增加语音白名单并完成实板闭环。
6. 实板验证成功后，再接 WSS/MQTT 云端链路。
7. 准备 5 分钟演示脚本，按小学组四项任务讲。

## 验证命令建议

后续目录建立后按需运行：

```bash
node --check dashboard/app.js
node --check dashboard/sw.js
python3 -m py_compile tools/n16r8_gateway.py
python3 -m py_compile tools/n16r8_cloud_relay.py
/Users/yukii/.platformio/penv/bin/pio run -d firmware
python3 tools/n16r8_gateway.py --mock-board --ws-port 18766
```

实板验证必须看到：

- 串口 `hello`。
- 持续变化的 `telemetry`。
- 网页命令返回 `ack`。
- 拔掉 USB 后 Dashboard 不显示假在线。
- 安全异常会覆盖普通手动控制。

## 变更同步规则

如果修改任一项，必须同步所有相关文件：

| 修改内容 | 必须同步 |
| --- | --- |
| GPIO 或模块角色 | `设计方案.md`、`开发文档.md`、`AGENTS.md`、固件、Dashboard、接线图说明 |
| topic 前缀 | `开发文档.md`、`AGENTS.md`、gateway、relay、Dashboard |
| JSON 字段 | 固件、gateway、Dashboard、测试、文档 |
| 语音意图 | Dashboard、小智/语音桥、文档、演示脚本 |
| 安全规则 | 固件、Dashboard、测试、文档 |

不要把 API key、MQTT 密码、Wi-Fi 密码写入文档或代码提交。
