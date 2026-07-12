# HK2 公网云桥与隔离部署设计

## 目标

在不影响服务器现有系统的前提下，为 `N16R8 智慧安心节能小屋` 增加 HTTPS Dashboard、WSS 云桥和独立 MQTT 通道。插板电脑上的 Chrome/Edge 通过 Web Serial 读取真实 N16R8 数据，并把协议帧转发到云端；其他浏览器通过同一公网页面查看实时状态并发送命令。

## 实板与身份合同

- `project`: `smartlife-primary-hk2`
- `profileId`: `smartlife-primary-safe-energy-home-v1`
- MQTT topic 前缀：`smartlife/primary/hk2/n16r8`
- 只接受 `hello`、`telemetry`、`health`、`event`、`ack`、`command`、`config`、`voiceIntent`、`ping`
- Dashboard 在线状态必须来自新鲜的真实 `hello` 或 `telemetry`，不能由 WSS 连接状态代替
- 云端命令必须经插板电脑写入 USB，并等待开发板真实 `ack` 或后续 `telemetry`

## 云桥数据流

```text
N16R8 USB
  -> Chrome/Edge Web Serial
  -> HTTPS Dashboard（USB 网关页面保持打开）
  -> WSS /smartlife-primary-hk2-ws
  -> HK2 独立 Relay
  -> HK2 独立 MQTT 19383
  -> 其他浏览器 Dashboard
```

每个浏览器生成独立 `originClientId`。USB 网关发出的帧使用 `origin=web-serial-gateway`；普通浏览器命令使用 `origin=dashboard`。客户端忽略自己的云端回声，写入串口前剥离 `origin`、`originClientId`、`mqttTopic`、`relayedAt` 等传输元数据。

## 服务器隔离合同

2026-07-12 已只读审计服务器现状。现有 `smartlife-junior-*`、`smartlife-primary-*`、Nginx 和 Docker 应用均保持不变。

| 资源 | HK2 独立值 |
| --- | --- |
| 项目目录 | `/home/ubuntu/smartlife-primary-hk2` |
| 静态站端口 | `127.0.0.1:19367` |
| WSS Relay 端口 | `127.0.0.1:19366` |
| MQTT 端口 | `127.0.0.1:19383` |
| 独立域名 | `hongkongxiao2.ilelezhan.cn`（已解析到服务器） |
| 公网页面 | `https://hongkongxiao2.ilelezhan.cn/` |
| WSS 路径 | `wss://hongkongxiao2.ilelezhan.cn/smartlife-primary-hk2-ws` |
| systemd 前缀 | `smartlife-primary-hk2-*` |

三个端口只监听回环地址，不直接暴露公网。Nginx 使用独立 `server_name hongkongxiao2.ilelezhan.cn`，不修改作品1域名的 `/` 首页和 `/smartlife-primary-ws`。变更前备份配置，变更后先运行 `nginx -t`，只执行平滑 reload，不 restart。TLS 证书只为新域名单独签发。

## 服务与文件

- `smartlife-primary-hk2-web.service`：只提供本项目 `dashboard/`
- `smartlife-primary-hk2-relay.service`：只处理 HK2 project/profile 和 topic
- `smartlife-primary-hk2-mqtt.service`：只监听 `127.0.0.1:19383`
- `deploy/nginx/hongkongxiao2.ilelezhan.cn.conf`：本项目独立域名 server block

MQTT 监听器仅限回环地址，因此首版不向公网开放 Broker。代码与 GitHub 中不得出现 SSH、Wi-Fi、MQTT 或其他密码。

## 验收

1. 本地 Dashboard、云桥与 relay 单元测试全部通过。
2. 三个 HK2 服务为 `active/running`，只监听 19366、19367、19383。
3. `https://hongkongxiao2.ilelezhan.cn/` 返回本项目页面和最新静态资源。
4. WSS 握手成功，Relay 报告 MQTT online。
5. USB 网关上传的真实帧可被第二浏览器接收；远程命令能返回真实 `ack`。
6. 原有 junior、primary、Docker 服务继续运行，既有首页与既有 WebSocket 路径可访问。
