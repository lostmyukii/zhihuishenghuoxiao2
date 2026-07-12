# HK2 独立部署

目标资源：

- 项目目录：`/home/ubuntu/smartlife-primary-hk2`
- Dashboard：`127.0.0.1:19367`
- Relay：`127.0.0.1:19366`
- MQTT：`127.0.0.1:19383`
- 公网：`https://hongkongxiao2.ilelezhan.cn/`

部署顺序：

1. 再次确认 19366、19367、19383 未被占用，并记录既有服务 PID。
2. 将本仓库同步到独立目录，创建 `.venv` 并安装 `deploy/requirements.txt`。
3. 复制 `deploy/hk2.env.template` 为 `deploy/.env`，权限设为 `600`。
4. 安装并启动三个 `smartlife-primary-hk2-*` systemd 服务，只验证回环端口。
5. 先启用 `hongkongxiao2-http-acme.conf`，运行 `nginx -t` 后平滑 reload。
6. 使用 Webroot 为新域名单独签发证书。
7. 将站点配置替换为 `hongkongxiao2.ilelezhan.cn.conf`，再次 `nginx -t` 后平滑 reload。
8. 验证 HTTPS、WSS、MQTT 状态、静态文件哈希和既有服务状态。

MQTT 仅监听 `127.0.0.1`，不对公网开放。不要把 SSH、Wi-Fi、MQTT 或其他密码写入仓库。
