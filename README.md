# 🔍 局域网设备扫描工具 (LAN Scanner)

一个基于 Web 界面的局域网设备扫描工具，用于快速发现和识别指定子网中的设备。

## 功能特点

- **Web 界面操作**：浏览器打开即可使用，无需命令行
- **可配置子网**：支持任意 /24 网段扫描（如 `192.168.1.x`、`192.168.2.x`）
- **MAC 地址过滤**：按 MAC 前缀筛选特定厂商或类型的设备
- **SSH 端口探测**：自动检测目标设备是否开放 SSH
- **SSH 登录验证**：尝试使用指定凭据登录，获取设备 hostname
- **Hostname 过滤**：按关键字筛选目标设备
- **实时进度与日志**：扫描过程实时展示，便于观察和排错

## 使用方法

### 快速启动（推荐）

双击 **`启动扫描工具.bat`**，浏览器会自动打开 Web 界面。

> 控制台窗口请保持开启，关闭即退出程序。

### 备选方式

如果 bat 文件不可用，也可双击 `局域网设备扫描工具.exe`（PyInstaller 打包），或手动运行：

```bash
python lan_scanner_web.py
```

### 常见问题

**Q: 双击后没反应？**

这个程序**不是传统桌面窗口程序**，而是一个 **Web 应用**。

双击运行后会：
1. 在后台启动一个本地 Web 服务器
2. 自动尝试打开浏览器访问 `http://127.0.0.1:5000`

如果觉得"没反应"，可以试试：

1. **检查任务管理器** — 确认 `python.exe` 或启动工具进程是否在后台运行
2. **手动打开浏览器**，访问 **http://127.0.0.1:5000**
3. 如果浏览器没有自动弹出，可手动输入上述地址

> 💡 控制台窗口会显示 Flask 的服务信息（`Running on http://127.0.0.1:5000`），**请不要关闭这个窗口**，关闭即退出程序。

### Web 界面配置

| 参数 | 说明 | 默认值 |
|------|------|--------|
| 子网 | 目标网段前3段 | `192.168.1` |
| MAC 前缀 | 只扫描此 MAC 开头的设备 | `fe:fd:fc` |
| SSH 用户名 | SSH 登录用户名 | `cat` |
| SSH 密码 | SSH 登录密码 | `temppwd` |
| SSH 端口 | SSH 服务端口 | `22` |
| Hostname 过滤 | 只显示 hostname 包含此关键字的设备 | `ph0v` |

点 **"开始扫描"** 即可，扫描完成后匹配的设备会高亮显示。

## 扫描流程

```
Ping 扫描 → 获取 MAC 地址 → MAC 过滤 → SSH 端口检测 → SSH 登录 → Hostname 过滤
```

## 技术栈

- **后端**: Python + Flask
- **前端**: HTML/CSS/JavaScript (原生)
- **SSH**: Paramiko
- **打包**: PyInstaller

## 文件结构

```
├── 启动扫描工具.bat           # ⭐ 推荐：双击启动
├── 局域网设备扫描工具.exe    # PyInstaller 打包（备选）
├── lan_scanner_web.py        # Python 后端源码
├── templates/
│   └── index.html            # Web 前端页面
├── README.md                 # 本文件
└── .gitignore                # Git 忽略规则
```

## 开发环境

- Python 3.8+
- Flask 3.x
- Paramiko 3.x
- PyInstaller 6.x

### 本地运行（不打包）

```bash
pip install flask paramiko
python lan_scanner_web.py
```

浏览器打开 `http://127.0.0.1:5000` 即可。

## License

MIT
