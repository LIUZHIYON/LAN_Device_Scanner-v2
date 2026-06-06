#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
局域网设备扫描工具 Web版
支持在浏览器中配置参数，实时查看扫描进度和结果
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
from flask import Flask, render_template, request, jsonify, Response

# ============ 全局状态 ============
SCAN_STATE = {
    "running": False,
    "progress": "",
    "phase": "",
    "results": [],
    "error": None,
    "log": []
}

def add_log(msg, level="info"):
    SCAN_STATE["log"].append({"msg": msg, "level": level, "time": time.strftime("%H:%M:%S")})
    if len(SCAN_STATE["log"]) > 500:
        SCAN_STATE["log"] = SCAN_STATE["log"][-500:]

def reset_state():
    SCAN_STATE["running"] = False
    SCAN_STATE["progress"] = ""
    SCAN_STATE["phase"] = ""
    SCAN_STATE["results"] = []
    SCAN_STATE["error"] = None
    SCAN_STATE["log"] = []

# ============ 扫描工具函数 ============

def ping_one(ip, timeout_ms=300):
    try:
        if sys.platform == "win32":
            cmd = ["ping", "-n", "1", "-w", str(timeout_ms), ip]
        else:
            cmd = ["ping", "-c", "1", "-W", str(max(1, timeout_ms // 1000)), ip]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=max(2, timeout_ms // 500))
        return result.returncode == 0
    except:
        return False


def ping_sweep(subnet, timeout_ms=300, progress_cb=None):
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
            if f.result():
                alive.append(ip)
            if progress_cb and done_count % 10 == 0:
                progress_cb(f"Ping: {done_count}/{total}", done_count / total)
    return alive


def get_arp_table(subnet):
    arp = {}
    try:
        output = subprocess.run(["arp", "-a"], capture_output=True, text=True, timeout=5).stdout
    except:
        output = ""

    for line in output.splitlines():
        m = re.search(r'(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F]{2}[-:][0-9a-fA-F]{2}[-:][0-9a-fA-F]{2}[-:][0-9a-fA-F]{2}[-:][0-9a-fA-F]{2}[-:][0-9a-fA-F]{2})', line)
        if m:
            ip_raw = m.group(1)
            mac_raw = m.group(2).replace("-", ":").lower()
            if ip_raw.startswith(subnet) and ip_raw not in arp:
                arp[ip_raw] = mac_raw

    if sys.platform == "win32":
        try:
            output2 = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"Get-NetNeighbor -IPAddress '{subnet}.*' | Select-Object IPAddress, LinkLayerAddress"],
                capture_output=True, text=True, timeout=10
            ).stdout
            for line in output2.splitlines():
                m = re.search(r'(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F]{2}[-:][0-9a-fA-F]{2}[-:][0-9a-fA-F]{2}[-:][0-9a-fA-F]{2}[-:][0-9a-fA-F]{2}[-:][0-9a-fA-F]{2})', line)
                if m:
                    ip_raw = m.group(1)
                    mac_raw = m.group(2).replace("-", ":").lower()
                    if ip_raw not in arp:
                        arp[ip_raw] = mac_raw
        except:
            pass
    return arp


def check_port(ip, port, timeout_ms=1500):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout_ms / 1000.0)
        result = sock.connect_ex((ip, port))
        sock.close()
        return result == 0
    except:
        return False


def try_ssh_login(ip, user, password, port=22, timeout=5):
    try:
        import paramiko
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(ip, port=port, username=user, password=password, timeout=timeout)
        stdin, stdout, stderr = client.exec_command("hostname")
        hostname = stdout.read().decode().strip()
        client.close()
        return True, hostname
    except Exception as e:
        return False, str(e)


# ============ 扫描主流程（后台线程） ============

def run_scan(config):
    """在后台线程中执行扫描"""
    reset_state()
    SCAN_STATE["running"] = True

    subnet = config.get("subnet", "192.168.1").strip()
    mac_pre = config.get("mac_prefix", "fe:fd:fc").strip().lower().replace("-", ":").replace("_", ":")
    mac_pre_clean = mac_pre.rstrip(":")
    ssh_user = config.get("ssh_user", "cat")
    ssh_pass = config.get("ssh_pass", "temppwd")
    ssh_port = int(config.get("ssh_port", 22))
    host_filter = config.get("hostname_filter", "ph0v")
    ssh_only = config.get("ssh_only", False)
    timeout_ms = int(config.get("timeout", 1.5) * 1000)

    def set_progress(msg, pct=None):
        SCAN_STATE["phase"] = msg
        if pct is not None:
            SCAN_STATE["progress"] = f"{msg} ({int(pct*100)}%)"
        else:
            SCAN_STATE["progress"] = msg
        add_log(msg)

    try:
        add_log(f"开始扫描子网: {subnet}.0/24", "info")
        add_log(f"MAC过滤: {mac_pre_clean}..." if not ssh_only else "MAC过滤: 已跳过", "info")
        add_log(f"SSH: {ssh_user}@{subnet}.x:{ssh_port}", "info")

        # ---- Step 1: Ping ----
        set_progress("正在Ping扫描...")
        alive = ping_sweep(subnet, progress_cb=lambda msg, pct: set_progress(msg, pct))
        add_log(f"存活主机: {len(alive)} 台")

        # ---- Step 2: ARP ----
        set_progress("正在获取MAC地址...")
        arp_table = get_arp_table(subnet)
        add_log(f"ARP条目: {len(arp_table)} 个")

        if len(arp_table) < len(alive) // 2 and alive:
            set_progress("重新填充ARP表...")
            with ThreadPoolExecutor(max_workers=50) as ex:
                ex.map(lambda ip: ping_one(ip, 200), alive[:50])
            time.sleep(0.5)
            arp_table = get_arp_table(subnet)
            add_log(f"重新获取ARP: {len(arp_table)} 个")

        # ---- Step 3: MAC过滤 ----
        if ssh_only:
            set_progress("跳过MAC过滤...")
            candidates = [{"ip": ip, "mac": arp_table.get(ip, "unknown")} for ip in (alive or list(arp_table.keys()))]
        else:
            set_progress(f"过滤MAC前缀: {mac_pre_clean}...")
            candidates = []
            for ip, mac in arp_table.items():
                if mac.lower().startswith(mac_pre_clean):
                    candidates.append({"ip": ip, "mac": mac})
            if not candidates:
                # 再试一次
                with ThreadPoolExecutor(max_workers=50) as ex:
                    ex.map(lambda ip: ping_one(ip, 300), alive)
                time.sleep(1)
                arp_table = get_arp_table(subnet)
                for ip, mac in arp_table.items():
                    if mac.lower().startswith(mac_pre_clean) and not any(d["ip"] == ip for d in candidates):
                        candidates.append({"ip": ip, "mac": mac})

            add_log(f"MAC匹配: {len(candidates)} 台")

        if not candidates:
            SCAN_STATE["error"] = f"未找到MAC前缀为 [{mac_pre_clean}] 的设备"
            add_log(SCAN_STATE["error"], "error")
            SCAN_STATE["running"] = False
            return

        # ---- Step 4: 端口检查 ----
        set_progress(f"检查SSH端口 ({ssh_port})...")
        ssh_open = []
        for i, dev in enumerate(candidates):
            ip = dev["ip"]
            set_progress(f"检查SSH端口: {ip}", (i+1)/len(candidates))
            if check_port(ip, ssh_port, timeout_ms):
                ssh_open.append(dev)
                add_log(f"  ✅ {ip} SSH开放", "success")
            else:
                add_log(f"  ❌ {ip} SSH关闭", "warn")

        if not ssh_open:
            SCAN_STATE["error"] = f"没有设备开放SSH端口 ({ssh_port})"
            add_log(SCAN_STATE["error"], "error")
            SCAN_STATE["running"] = False
            return

        # ---- Step 5: SSH登录 ----
        set_progress("正在SSH登录测试...")
        logged_in = []
        for i, dev in enumerate(ssh_open):
            ip = dev["ip"]
            set_progress(f"SSH登录: {ip}", (i+1)/len(ssh_open))
            ok, hostname = try_ssh_login(ip, ssh_user, ssh_pass, ssh_port)
            if ok:
                dev["hostname"] = hostname
                logged_in.append(dev)
                add_log(f"  ✅ {ip} -> {hostname}", "success")
            else:
                add_log(f"  ❌ {ip} 登录失败: {hostname}", "warn")

        if not logged_in:
            SCAN_STATE["error"] = "没有设备能成功SSH登录"
            add_log(SCAN_STATE["error"], "error")
            SCAN_STATE["running"] = False
            return

        # ---- Step 6: Hostname过滤 ----
        set_progress("按hostname过滤...")
        filtered = [d for d in logged_in if host_filter.lower() in (d.get("hostname", "") or "").lower()]

        results = []
        if filtered:
            for d in filtered:
                results.append({
                    "ip": d["ip"],
                    "mac": d["mac"],
                    "hostname": d["hostname"],
                    "matched": True
                })
            add_log(f"✅ 找到 {len(filtered)} 台匹配设备 (hostname包含'{host_filter}')", "success")
        else:
            for d in logged_in:
                results.append({
                    "ip": d["ip"],
                    "mac": d["mac"],
                    "hostname": d["hostname"],
                    "matched": False
                })
            add_log(f"⚠️  没有hostname包含'{host_filter}'的设备", "warn")

        SCAN_STATE["results"] = results
        set_progress("扫描完成!")

    except Exception as e:
        SCAN_STATE["error"] = str(e)
        add_log(f"扫描出错: {e}", "error")
    finally:
        SCAN_STATE["running"] = False


# ============ Flask Web应用 ============

app = Flask(__name__)
app.config['SECRET_KEY'] = 'lan-scanner-secret-key'


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/scan', methods=['POST'])
def api_scan():
    if SCAN_STATE["running"]:
        return jsonify({"status": "error", "message": "扫描正在进行中，请等待完成"})

    config = request.json or {}
    t = threading.Thread(target=run_scan, args=(config,), daemon=True)
    t.start()
    return jsonify({"status": "ok", "message": "扫描已启动"})


@app.route('/api/status')
def api_status():
    return jsonify({
        "running": SCAN_STATE["running"],
        "progress": SCAN_STATE["progress"],
        "phase": SCAN_STATE["phase"],
        "results": SCAN_STATE["results"],
        "error": SCAN_STATE["error"],
        "log": SCAN_STATE["log"][-50:]  # 最近50条
    })


@app.route('/api/stop', methods=['POST'])
def api_stop():
    # 不能真正停止线程，但标记让用户知道已请求停止
    SCAN_STATE["running"] = False
    SCAN_STATE["error"] = "用户手动停止"
    add_log("用户手动停止扫描", "warn")
    return jsonify({"status": "ok", "message": "已请求停止"})


# ============ 主入口 ============

if __name__ == '__main__':
    port = 5000
    url = f"http://127.0.0.1:{port}"

    print("=" * 50)
    print("   局域网设备扫描工具 - Web版")
    print("=" * 50)
    print(f"   浏览器访问: {url}")
    print("=" * 50)
    print("   关闭此窗口即可退出程序")
    print("=" * 50)

    app.run(host="127.0.0.1", port=port, debug=False)


    app.run(host="127.0.0.1", port=port, debug=False)
