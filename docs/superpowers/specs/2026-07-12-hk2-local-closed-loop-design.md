# N16R8 智慧安心节能小屋本地完整闭环设计

日期：2026-07-12

状态：设计已确认，等待实施

## 1. 目标与复用原则

第一阶段把 `香港小学作品2` 开发到可现场演示、可自动验证、可实板验收的本地完整闭环：

```text
稳定固件 + 本地 Web Serial Dashboard + mock 网关 + 自动测试 + 实板烧录验证
```

实现采用“受控迁移香港小学作品1架构”路线：复用作品1已经验证的固件分层、Dashboard 纯逻辑模块、Web Serial、告警解释、节能原因、语音白名单、mock 网关和测试方法，但不复制作品1的项目标识、模式名称、GPIO、MQTT topic、域名、端口或部署状态。

第一阶段不做公网部署。WSS/MQTT 状态只显示“未配置”，不连接作品1的云端服务。公网链路在本地与实板闭环通过后另开设计与实施步骤。

## 2. 项目身份

| 项目 | 值 |
| --- | --- |
| 作品名称 | `N16R8 智慧安心节能小屋` |
| project | `smartlife-primary-hk2` |
| profileId | `smartlife-primary-safe-energy-home-v1` |
| 串口 | `115200`，每行一个 JSON |
| 本地路线 | Chrome/Edge Web Serial |
| 后续 MQTT 前缀 | `smartlife/primary/hk2/n16r8` |

所有 Dashboard、mock、固件和测试必须使用上述身份，不得残留作品1的 `smartlife-primary`、`smartlife-primary-study-home-v1`、公网域名或 `19266/19267/19283` 部署配置。

## 3. 冻结硬件合同

| 模块 | GPIO/接口 | 第一阶段行为 |
| --- | --- | --- |
| 光敏传感器 | `ADC1 / GPIO1` | 光照采集、光暗开灯、节能判断 |
| MQ-2 AO | `ADC2 / GPIO2` | 烟雾/燃气阈值告警；AO 已确认限制在 `0~3.3V` |
| 声音传感器 | `ADC4 / GPIO4` | 学习模式噪声提醒 |
| PIR 人体红外 | `D5 / GPIO5` | 有人/无人、离家入侵、节能判断 |
| 水滴传感器 | `D8 / GPIO8` | 漏水告警；默认高电平触发，实板空闲电平验收时复核 |
| 火焰传感器 DO/SIG | `GPIO11` | `INPUT_PULLUP`，低电平触发；AO 不接 |
| 学习灯/低压继电器 | `D12 / GPIO12` | 自动照明和十秒手动测试；不接 `220V` |
| 无源蜂鸣器 | `D13 / GPIO13` | 舒适提醒和安全告警 |
| DHT11 | `D14 / GPIO14` | 温湿度与舒适阈值 |
| OLED | `SDA=GPIO41, SCL=GPIO42` | 模式、传感、学习灯和告警本地显示 |

当前实物没有 8 键 AD、风扇、舵机和 RGB。固件、`hello/telemetry`、Dashboard、mock、语音和验收不得声明这些模块。

## 4. 总体架构与数据流

```text
N16R8 实板
  -> 115200 单行 JSON
  -> Chrome/Edge Web Serial
  -> 本地 Dashboard 状态与操作

无实板验收：
mock board -> 本地 WebSocket -> 同一 Dashboard 协议入口

第二阶段才增加：
USB Dashboard -> WSS Relay -> MQTT -> 远端 Dashboard
```

固件是模式、告警、执行器和真实在线状态的权威来源。Dashboard 只能根据新鲜 `hello/telemetry/ack` 更新状态；点击按钮本身不能伪装模式或执行器已经成功变化。

## 5. 固件设计

### 5.1 采样周期

- 光敏、声音、PIR、MQ-2、水滴和火焰使用独立快速采样路径，每 `200ms` 更新。
- DHT11 每 `2000ms` 读取一次。
- DHT11 成功后保存最近有效温湿度和成功时间。
- 单次失败保留最近有效值；启动从未成功或连续约 `6000ms` 未成功才设置 `dhtValid=false`。
- 遥测每 `1000ms` 输出一次，命令处理后立即返回 `ack`。

### 5.2 模式规则

| 模式 | 学习灯 | 普通提醒 |
| --- | --- | --- |
| `home` | 有人且光线暗时开启 | 常规采集；PIR 不作为入侵 |
| `study` | 光线暗时开启 | 噪声或有效温度超阈值产生橙色提醒 |
| `away` | 强制关闭 | PIR 检测到人体产生红色入侵告警 |
| `energy` | 仅有人且光线暗时开启 | 输出中文节能原因和节能分 |

### 5.3 告警优先级

1. MQ-2、火焰、水滴安全告警。
2. `away` 模式 PIR 入侵。
3. `study` 模式噪声、温度舒适提醒。
4. 模式自动控制。
5. 手动测试命令。

标准告警代码为：

```text
mq2 / flame / water / intrusion / noise / temperature
```

安全告警时，如果 `buzzerEnabled=true`，蜂鸣器必须响。`actuator.buzzer=false` 只停止手动蜂鸣测试，不关闭自动安全告警；只有 `set.buzzerEnabled=false` 才是明确安全静音。

### 5.4 手动测试

Dashboard 可发送：

```json
{"type":"command","actuator":{"lamp":true}}
{"type":"command","actuator":{"lamp":false}}
{"type":"command","actuator":{"buzzer":true}}
{"type":"command","actuator":{"buzzer":false}}
```

执行器测试使用作品1已验证的十秒手动覆盖窗口；窗口结束后自动回到当前模式规则。安全告警可以覆盖手动关闭蜂鸣器。切换模式立即清除手动覆盖。

### 5.5 OLED 与健康状态

OLED 使用 `0x3C`，显示六行以内的英文缩写和数值，至少包含：当前模式、光照/人体、温湿度、学习灯、蜂鸣器或最高优先级告警。

协议必须公开：

- `display.lines`
- `health.dht=ok/missing`
- `health.oled=ready/missing`
- `health.buzzer=enabled/muted`
- `health.uptimeMs`

## 6. 串口协议

启动帧必须包含真实 GPIO 和能力：

```json
{"type":"hello","project":"smartlife-primary-hk2","profileId":"smartlife-primary-safe-energy-home-v1","board":"n16r8_esp32s3","baud":115200,"pins":{"light":1,"mq2":2,"sound":4,"pir":5,"water":8,"flame":11,"lamp":12,"buzzer":13,"dht":14,"oledSda":41,"oledScl":42}}
```

遥测结构：

```json
{"type":"telemetry","mode":"study","sensors":{"light":32,"sound":18,"temperature":28.4,"humidity":56,"pir":true,"mq2":21,"water":false,"flame":false},"actuators":{"lamp":true,"buzzer":false},"alerts":[],"energy":{"score":88,"reason":"光线不足，已开启学习灯"},"display":{"lines":[]},"health":{"profileId":"smartlife-primary-safe-energy-home-v1","dht":"ok","oled":"ready","buzzer":"enabled"}}
```

命令必须支持：

- `mode=home/study/away/energy`
- `lightThreshold`
- `temperatureThreshold`
- `soundThreshold`
- `mq2Threshold`
- `buzzerEnabled`
- `actuator.lamp`
- `actuator.buzzer`
- 白名单 `voiceIntent`

未知命令返回 `{"type":"ack","ok":false,"message":"unknown-command"}`。

## 7. Dashboard 设计

### 7.1 信息结构

桌面使用左宽右窄双栏，日志跨满底部：

```text
┌────────────────────────────────────────────┐
│ 项目名 │ USB │ 开发板 │ 最新帧 │ 当前模式 │
├──────────────────────────┬─────────────────┤
│ 安心状态带               │ 学生操作台      │
│ 正常/提醒/安全告警原因    │ 连接 USB        │
├──────────────────────────┤ 四种模式        │
│ 八类传感器实时卡片       │ 阈值调整        │
│ 光/温湿/声音/PIR         │ 学习灯测试      │
│ MQ-2/水滴/火焰           │ 安全静音        │
├──────────────────────────┤ 语音/文本意图   │
│ OLED 本地屏预览          │ 节能分与原因    │
├──────────────────────────┴─────────────────┤
│ hello / telemetry / ack / event 日志       │
└────────────────────────────────────────────┘
```

### 7.2 可见状态

- 蓝色：当前模式正在使用的传感器；真实模式变化时闪烁约 `2200ms`，随后保持柔和蓝色。
- 绿色：数据新鲜且无提醒/告警。
- 橙色：`noise/temperature` 舒适提醒。
- 红色：`mq2/flame/water/intrusion` 安全告警。
- 灰色：没有新鲜遥测，显示“等待 N16R8”。

告警原因必须包含中文原因、来源 GPIO、当前值和阈值（适用时）以及真实动作。未上报告警时，不根据原始 PIR 或 MQ-2 数值自行制造红色状态。

### 7.3 页面模块

- `alert-core.js`：模式关联传感器、告警代码、中文原因、严重度和动作说明。
- `energy-core.js`：离线等待、节能分和中文节能原因。
- `intent-core.js`：文本/语音白名单，只产生安全命令。
- `app.js`：Web Serial、状态新鲜度、渲染、命令发送和日志。
- `index.html` / `style.css`：双栏操作台和 `390px` 单栏布局。

本阶段 WSS/MQTT 显示“未配置”，不加载作品1的 `cloud-core.js` 连接配置。后续上云时再新增独立 `cloud-core.js` 和 Relay。

### 7.4 浏览器与无障碍

- USB 直连只承诺 HTTPS/localhost 下的 Chrome 或 Edge。
- Safari、Firefox 和手机浏览器本阶段不承担 USB 网关角色。
- `390px` 宽度必须无横向滚动。
- 所有按钮有清晰键盘焦点；告警区域使用 `role=status` 和 `aria-live=polite`。
- 支持 `prefers-reduced-motion`。

## 8. mock 网关

`tools/n16r8_gateway.py --mock-board` 必须产生与实板相同的 `project/profileId/hello/telemetry/ack` 结构，支持：

- 四种模式。
- 四项阈值。
- 学习灯和蜂鸣器手动测试。
- `mq2/flame/water/intrusion/noise/temperature` 场景。
- `display.lines` 和健康状态。

mock 只用于页面和命令验收，UI 与文档必须明确标记“模拟数据”，不能写成实板通过。

## 9. 自动验证与实板验收

### 9.1 自动验证

```bash
node --check dashboard/app.js
node --check dashboard/alert-core.js
node --check dashboard/energy-core.js
node --check dashboard/intent-core.js
node dashboard/tests/alert-core.test.js
node dashboard/tests/energy-core.test.js
node dashboard/tests/voice-intent.test.js
node dashboard/tests/layout-contract.test.js
python3 -m py_compile tools/n16r8_gateway.py tools/ws_json.py
PYTHONPATH=tools python3 -m unittest tools/test_gateway.py tools/test_firmware_contract.py
/Users/yukii/.platformio/penv/bin/pio run -d firmware
git diff --check
```

合同测试必须明确拒绝 8 键、风扇、舵机、RGB、`GPIO48` 学习灯和 `GPIO6` 火焰字段。

### 9.2 实板验收

1. 关闭可能占用串口的 Dashboard/Monitor，烧录固件。
2. 串口看到真实 `hello` 和连续变化的 `telemetry`。
3. Dashboard 授权 Web Serial，确认新鲜在线状态。
4. 依次验证光敏、DHT11、声音、PIR、MQ-2、水滴和火焰。
5. 验证 `GPIO12` 学习灯、`GPIO13` 蜂鸣器和 OLED。
6. 临时调整阈值验证提醒与恢复，再恢复默认阈值。
7. 拔掉 USB，Dashboard 必须在约 `3.5s` 内显示离线。

火焰不用明火，可用安全红外源或遮挡/模块测试方式。MQ-2 不使用危险烟气演示。水滴测试避免液体接触主板和裸露供电线。

## 10. 分步实施与 GitHub 提交

每一步完成、验证后立即单独提交并推送：

1. **固件闭环**：稳定采样、OLED、GPIO12、GPIO11、告警和协议；更新固件测试。
2. **本地 Dashboard**：Web Serial、安心状态带、传感器、模式、阈值、执行器、语音和布局测试。
3. **mock 网关**：同协议模拟、场景命令和 Python 测试。
4. **实板验收**：烧录、串口/Web Serial 证据和文档记录。

任何一步推送失败时停止后续实施，先恢复 GitHub 同步。

## 11. 文件范围

第一阶段允许修改或新增：

```text
firmware/platformio.ini
firmware/src/main.cpp
dashboard/*
dashboard/tests/*
tools/n16r8_gateway.py
tools/ws_json.py
tools/test_gateway.py
tools/test_firmware_contract.py
AGENTS.md
开发文档.md
设计方案.md
docs/superpowers/specs/*
```

第一阶段不创建或修改公网部署、Nginx、systemd、云服务器、MQTT 密码和作品1仓库文件。

## 12. 完成标准

- 所有自动检查通过。
- Dashboard 在无数据、mock 和实板三种状态下语义清楚。
- 实板产生真实 `hello/telemetry/ack`，七类外部传感输入、学习灯、蜂鸣器和 OLED 均完成验证。
- 作品2的四项小学任务可在五分钟内从真实硬件、OLED、Dashboard 和事件日志中讲清。
- 本地仓库与 `origin/main` 同步。

## 13. 非目标

- 本阶段不做公网 WSS/MQTT 部署。
- 不增加板端 Wi-Fi/MQTT 固件。
- 不增加自由文本危险控制。
- 不恢复八键、风扇、舵机或 RGB。
- 不把 mock 结果写成实板验收。
