#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
局域网设备扫描工具 Web版 v2.1
支持在浏览器中配置参数，实时查看扫描进度和结果

性能优化:
- 端口预检: 先用socket快速检测SSH端口(1.5s超时), 再对开放端口设备进行SSH登录(5s超时)
- 并行ARP: Windows上同时运行 arp -a 和 Get-NetNeighbor, 减少等待时间
- 可停止扫描: 各阶段检查停止标志, 用户可随时中断
- 优化MAC重试: 仅重试缺失的IP, 不再全量重扫
- 预编译正则: 避免重复编译ARP解析正则
"""

import os
import sys
import json
import time
import threading
import socket
import subprocess
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, render_template, request, jsonify

# ============ 全局状态 ============
SCAN_STATE = {
    "running": False,
    "progress": "",
    "phase": "",
    "results": [],
    "error": None,
    "log": [],
    "start_time": 0,
}


class ScanAborted(Exception):
    """扫描被用户中止"""
    pass


def add_log(msg, level="info"):
    SCAN_STATE["log"].append({
        "msg": msg, "level": level,
        "time": time.strftime("%H:%M:%S")
    })
    if len(SCAN_STATE["log"]) > 500:
        SCAN_STATE["log"] = SCAN_STATE["log"][-500:]


def reset_state():
    SCAN_STATE["running"] = False
    SCAN_STATE["progress"] = ""
    SCAN_STATE["phase"] = ""
    SCAN_STATE["results"] = []
    SCAN_STATE["error"] = None
    SCAN_STATE["log"] = []
    SCAN_STATE["start_time"] = time.time()


def _check_stop():
    """检查是否被用户停止, 是则抛出 ScanAborted"""
    if not SCAN_STATE["running"]:
        raise ScanAborted("用户手动停止")


# ============ 扫描工具函数 ============

def ping_one(ip, timeout_ms=300):
    """单次ICMP Ping检测"""
    try:
        if sys.platform == "win32":
            cmd = ["ping", "-n", "1", "-w", str(timeout_ms), ip]
        else:
            cmd = ["ping", "-c", "1", "-W", str(max(1, timeout_ms // 1000)), ip]
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=max(2, timeout_ms // 500)
        )
        return result.returncode == 0
    except Exception:
        return False


def ping_sweep(subnet, timeout_ms=300, progress_cb=None):
    """并行Ping扫描整个/24子网, 返回存活IP列表"""
    alive = []
    total = 254
    with ThreadPoolExecutor(max_workers=100) as executor:
        futures = {}
        for octet in range(1, 255):
            ip = f"{subnet}.{octet}"
            futures[executor.submit(ping_one, ip, timeout_ms)] = ip
        done_count = 0
        for f in as_completed(futures):
            ip = futures[f]
            done_count += 1
            try:
                if f.result():
                    alive.append(ip)
            except Exception:
                pass
            if progress_cb and done_count % 10 == 0:
                progress_cb(f"Ping: {done_count}/{total}", done_count / total)
    return alive


# 预编译正则: 解析IP和MAC地址
_ARP_RE = re.compile(
    r'(\d+\.\d+\.\d+\.\d+)\s+'
    r'([0-9a-fA-F]{2}[-:][0-9a-fA-F]{2}[-:][0-9a-fA-F]{2}[-:]'
    r'[0-9a-fA-F]{2}[-:][0-9a-fA-F]{2}[-:][0-9a-fA-F]{2})'
)


def _parse_arp_output(output, subnet):
    """从命令行输出解析 IP → MAC 映射"""
    arp = {}
    for line in output.splitlines():
        m = _ARP_RE.search(line)
        if m:
            ip_raw = m.group(1)
            mac_raw = m.group(2).replace("-", ":").lower()
            if ip_raw.startswith(subnet) and ip_raw not in arp:
                arp[ip_raw] = mac_raw
    return arp


def get_arp_table(subnet):
    """获取ARP表, Windows上并行执行 arp -a 和 Get-NetNeighbor"""
    arp = {}

    def _run_arp_a():
        try:
            return subprocess.run(
                ["arp", "-a"], capture_output=True, text=True, timeout=5
            ).stdout
        except Exception:
            return ""

    def _run_powershell():
        if sys.platform != "win32":
            return ""
        try:
            return subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"Get-NetNeighbor -IPAddress '{subnet}.*' | "
                 f"Select-Object IPAddress, LinkLayerAddress"],
                capture_output=True, text=True, timeout=8
            ).stdout
        except Exception:
            return ""

    # 并行执行两个命令, 减少总等待时间
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_arp = ex.submit(_run_arp_a)
        f_ps = ex.submit(_run_powershell)

        arp_output = f_arp.result()
        arp = _parse_arp_output(arp_output, subnet)

        ps_output = f_ps.result()
        if ps_output:
            ps_arp = _parse_arp_output(ps_output, subnet)
            for ip, mac in ps_arp.items():
                if ip not in arp:
                    arp[ip] = mac

    return arp


def check_port(ip, port, timeout_ms=1500):
    """快速TCP端口连通性检测 (socket级别, 比SSH登录快得多)"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout_ms / 1000.0)
        result = sock.connect_ex((ip, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def try_ssh_login(ip, user, password, port=22, timeout=5):
    """SSH登录并获取hostname, 返回 (success: bool, hostname_or_error: str)"""
    try:
        import paramiko
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            ip, port=port, username=user, password=password,
            timeout=timeout, banner_timeout=timeout, auth_timeout=timeout
        )
        stdin, stdout, stderr = client.exec_command("hostname", timeout=timeout)
        hostname = stdout.read().decode().strip()
        client.close()
        return True, hostname
    except Exception as e:
        return False, str(e)


# ============ 扫描主流程 (后台线程) ============

def run_scan(config):
    """在后台线程中执行完整扫描流程"""
    reset_state()
    SCAN_STATE["running"] = True
    SCAN_STATE["start_time"] = time.time()

    # --- 解析配置 ---
    subnet = config.get("subnet", "192.168.1").strip()
    mac_pre = config.get("mac_prefix", "fe:fd:fc").strip().lower() \
                   .replace("-", ":").replace("_", ":")
    mac_pre_clean = mac_pre.rstrip(":")
    ssh_user = config.get("ssh_user", "cat")
    ssh_pass = config.get("ssh_pass", "temppwd")
    ssh_port = int(config.get("ssh_port", 22))
    host_filter = config.get("hostname_filter", "ph0v")
    ssh_only = config.get("ssh_only", False)
    timeout_ms = int(config.get("timeout", 1.5) * 1000)

    def set_progress(msg, pct=None):
        _check_stop()
        SCAN_STATE["phase"] = msg
        SCAN_STATE["progress"] = msg if pct is None else f"{msg} ({int(pct * 100)}%)"
        add_log(msg)

    try:
        # 启动信息
        add_log(f"开始扫描子网: {subnet}.0/24", "info")
        mac_info = f"MAC过滤: {mac_pre_clean}..." if not ssh_only else "MAC过滤: 已跳过"
        add_log(mac_info, "info")
        add_log(f"SSH: {ssh_user}@{subnet}.x:{ssh_port}", "info")

        # ===== Step 1: Ping 扫描 =====
        set_progress("正在Ping扫描...")

        def ping_progress(msg, pct):
            _check_stop()
            SCAN_STATE["phase"] = msg
            SCAN_STATE["progress"] = msg if pct is None else f"{msg} ({int(pct * 100)}%)"

        alive = ping_sweep(subnet, timeout_ms=timeout_ms,
                           progress_cb=lambda msg, pct: ping_progress(msg, pct * 0.2))
        add_log(f"存活主机: {len(alive)} 台", "success")
        _check_stop()

        if not alive:
            SCAN_STATE["error"] = "未发现存活主机"
            add_log(SCAN_STATE["error"], "error")
            return

        # ===== Step 2: ARP 获取 (并行 arp -a + Get-NetNeighbor) =====
        set_progress("正在获取MAC地址...")
        arp_table = get_arp_table(subnet)
        add_log(f"ARP条目: {len(arp_table)} 个")
        _check_stop()

        # ARP表太稀疏时重新填充
        if len(arp_table) < len(alive) // 2 and alive:
            set_progress("重新填充ARP表...")
            with ThreadPoolExecutor(max_workers=100) as ex:
                ex.map(lambda ip: ping_one(ip, 200), alive[:50])
            time.sleep(0.5)
            arp_table = get_arp_table(subnet)
            add_log(f"重新获取ARP: {len(arp_table)} 个")
        _check_stop()

        # ===== Step 3: MAC 过滤 =====
        if ssh_only:
            set_progress("跳过MAC过滤...")
            candidates = [
                {"ip": ip, "mac": arp_table.get(ip, "unknown")}
                for ip in alive
            ]
        else:
            set_progress(f"过滤MAC前缀: {mac_pre_clean}...")
            candidates = [
                {"ip": ip, "mac": mac}
                for ip, mac in arp_table.items()
                if mac.lower().startswith(mac_pre_clean)
            ]

            # 无匹配时: 仅重试缺失的IP, 不全量重扫
            if not candidates:
                _check_stop()
                set_progress("MAC无匹配, 重新探测缺失设备...")
                missing = [ip for ip in alive if ip not in arp_table]
                if missing:
                    with ThreadPoolExecutor(max_workers=100) as ex:
                        ex.map(lambda ip: ping_one(ip, 300), missing[:50])
                    time.sleep(1)
                    arp_table2 = get_arp_table(subnet)
                    for ip, mac in arp_table2.items():
                        if mac.lower().startswith(mac_pre_clean) and \
                           not any(d["ip"] == ip for d in candidates):
                            candidates.append({"ip": ip, "mac": mac})

            add_log(f"MAC匹配: {len(candidates)} 台")

        _check_stop()

        if not candidates:
            SCAN_STATE["error"] = f"未找到MAC前缀为 [{mac_pre_clean}] 的设备"
            add_log(SCAN_STATE["error"], "error")
            return

        # ===== Step 4: 端口预检 (socket快速过滤, 避免SSH超时等待) =====
        # 这是最大的性能优化: 先用1.5s超时的socket检测端口,
        # 只对端口确实开放的设备进行5s超时的SSH登录
        set_progress(f"正在检测SSH端口 ({len(candidates)}台)...")

        port_open = []
        port_closed = []

        with ThreadPoolExecutor(max_workers=min(50, len(candidates))) as executor:
            future_map = {
                executor.submit(check_port, dev["ip"], ssh_port, 1500): dev
                for dev in candidates
            }
            for i, f in enumerate(as_completed(future_map)):
                _check_stop()
                dev = future_map[f]
                try:
                    if f.result():
                        port_open.append(dev)
                        add_log(f"  🔍 {dev['ip']} SSH端口开放", "info")
                    else:
                        port_closed.append(dev)
                        add_log(f"  ⛔ {dev['ip']} SSH端口关闭", "warn")
                except Exception:
                    port_closed.append(dev)
                set_progress(
                    f"端口检测: {i + 1}/{len(candidates)}",
                    0.3 + (i + 1) / len(candidates) * 0.1
                )

        _check_stop()
        add_log(f"端口开放: {len(port_open)}台, 关闭: {len(port_closed)}台")

        if not port_open:
            SCAN_STATE["error"] = "所有候选设备SSH端口均未开放"
            add_log(SCAN_STATE["error"], "error")
            return

        # ===== Step 5: SSH 登录验证 =====
        set_progress(f"正在SSH登录 ({len(port_open)}台)...")
        logged_in = []
        login_lock = threading.Lock()

        def try_login_one(dev):
            ip = dev["ip"]
            ok, result = try_ssh_login(ip, ssh_user, ssh_pass, ssh_port)
            with login_lock:
                if ok:
                    dev["hostname"] = result
                    logged_in.append(dev)
                    add_log(f"  ✅ {ip} -> {result}", "success")
                elif any(kw in result for kw in
                         ["Authentication", "Permission", "denied"]):
                    add_log(f"  ❌ {ip} SSH登录失败: {result[:80]}", "warn")
                else:
                    add_log(f"  ⚠️  {ip} SSH不可达: {result[:80]}", "warn")

        with ThreadPoolExecutor(max_workers=min(20, len(port_open))) as executor:
            future_list = [
                executor.submit(try_login_one, dev) for dev in port_open
            ]
            for i, f in enumerate(as_completed(future_list)):
                _check_stop()
                try:
                    f.result()
                except Exception:
                    pass
                set_progress(
                    f"SSH登录: {i + 1}/{len(port_open)}",
                    0.4 + (i + 1) / len(port_open) * 0.4
                )

        if not logged_in:
            SCAN_STATE["error"] = "没有设备能成功SSH登录"
            add_log(SCAN_STATE["error"], "error")
            return

        # ===== Step 6: Hostname 过滤 =====
        set_progress("按hostname过滤...")
        filtered = [
            d for d in logged_in
            if host_filter.lower() in (d.get("hostname", "") or "").lower()
        ]

        results = []
        if filtered:
            for d in filtered:
                results.append({
                    "ip": d["ip"], "mac": d["mac"],
                    "hostname": d["hostname"], "matched": True
                })
            add_log(
                f"✅ 找到 {len(filtered)} 台匹配设备 "
                f"(hostname包含'{host_filter}')",
                "success"
            )
        else:
            for d in logged_in:
                results.append({
                    "ip": d["ip"], "mac": d["mac"],
                    "hostname": d["hostname"], "matched": False
                })
            add_log(
                f"⚠️  没有hostname包含'{host_filter}'的设备, "
                f"显示全部 {len(logged_in)} 台已登录设备",
                "warn"
            )

        SCAN_STATE["results"] = results

        elapsed = time.time() - SCAN_STATE["start_time"]
        set_progress(f"扫描完成! 耗时 {elapsed:.1f}秒")

    except ScanAborted:
        add_log("⏹ 扫描已被用户停止", "warn")
        SCAN_STATE["error"] = "用户手动停止"
    except Exception as e:
        SCAN_STATE["error"] = str(e)
        add_log(f"扫描出错: {e}", "error")
    finally:
        SCAN_STATE["running"] = False


# ============ Flask Web 应用 ============

app = Flask(__name__)
app.config['SECRET_KEY'] = 'lan-scanner-secret-key-v2'


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/scan', methods=['POST'])
def api_scan():
    if SCAN_STATE["running"]:
        return jsonify({"status": "error", "message": "扫描正在进行中, 请等待完成"})

    config = request.json or {}
    t = threading.Thread(target=run_scan, args=(config,), daemon=True)
    t.start()
    return jsonify({"status": "ok", "message": "扫描已启动"})


@app.route('/api/status')
def api_status():
    elapsed = 0
    if SCAN_STATE["start_time"]:
        elapsed = time.time() - SCAN_STATE["start_time"]

    return jsonify({
        "running": SCAN_STATE["running"],
        "progress": SCAN_STATE["progress"],
        "phase": SCAN_STATE["phase"],
        "results": SCAN_STATE["results"],
        "error": SCAN_STATE["error"],
        "log": SCAN_STATE["log"][-50:],
        "elapsed": round(elapsed, 1),
    })


@app.route('/api/stop', methods=['POST'])
def api_stop():
    if SCAN_STATE["running"]:
        SCAN_STATE["running"] = False
        SCAN_STATE["error"] = "用户手动停止"
        add_log("⏹ 用户手动停止扫描", "warn")
    return jsonify({"status": "ok", "message": "已请求停止"})


# ============ 主入口 ============

if __name__ == '__main__':
    port = 5800
    url = f"http://127.0.0.1:{port}"

    print("=" * 50)
    print("   局域网设备扫描工具 - Web版 v2.1")
    print("=" * 50)
    print(f"   浏览器访问: {url}")
    print("=" * 50)
    print("   关闭此窗口即可退出程序")
    print("=" * 50)

    app.run(host="127.0.0.1", port=port, debug=False)
