import socket
import ssl
import threading
import time
import random
import json
from concurrent.futures import ThreadPoolExecutor
import os


def is_http_service(ip, port, timeout=2):
    """判断指定端口是否为HTTP服务（逻辑不变）"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect((ip, port))
            s.send(b"GET / HTTP/1.1\r\nHost: %s\r\n\r\n" % ip.encode())
            response = s.recv(1024)
            if response.startswith(b"HTTP/"):
                return "HTTP"
    except:
        pass

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect((ip, port))
            context = ssl.create_default_context()
            with context.wrap_socket(s, server_hostname=ip) as ssl_sock:
                ssl_sock.send(b"GET / HTTP/1.1\r\nHost: %s\r\n\r\n" % ip.encode())
                response = ssl_sock.recv(1024)
                if response.startswith(b"HTTP/"):
                    return "HTTPS"
    except Exception:
        pass

    return "未识别的服务"


def scan_port(ip, port, timeout=3):
    """扫描单个端口是否开放（逻辑不变）"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            result = s.connect_ex((ip, port))
            if result == 0:
                service_type = is_http_service(ip, port, timeout)
                return True, service_type if service_type else "Unknown"
            return False, None
    except Exception:
        return False, None


class GetPort:
    def __init__(self, ip, dl, mac):
        # 原有类属性结构完全保留
        self.dl = dl
        self.mac = mac
        self.port_list = {}
        self.ip = ip
        self.mode = True
        random.seed(mac)
        self.name = str(random.randint(10000000000000000000, 99999999999999999999))

        # 优化相关属性（延续之前配置）
        self.lock = threading.Lock()
        self.max_port_list2_len = 1000
        self.scan_rounds = 5  # 每轮扫描次数
        self.scan_interval = 10  # 轮次间休眠时间（秒）
        self.last_scan_time = {}
        self.last_saved_port_list2 = None

        # 原有port_list2初始化逻辑保留（从文件加载或用默认值）
        try:
            with open('devices/' + self.name) as f:
                self.port_list2 = json.load(f)
        except Exception:
            self.port_list2 = [8080, 5000, 1314]

        # 原有线程启动逻辑保留
        threading.Thread(target=self.start).start()
        threading.Thread(target=self.save).start()

    def start(self):
        # 线程池配置不变（按CPU核心数×5设置）
        max_workers = os.cpu_count() * 5 if os.cpu_count() else 10
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 核心调整：拆分“原有端口”和“其他端口段”，分别提交任务
            # 1. 提交“原有端口”扫描任务（第一优先级，单独线程处理）
            executor.submit(self.scan_priority_ports)

            # 2. 提交“其他端口段”扫描任务（第二优先级，打乱顺序后随机扫描）
            # 低速段：10000~65535（分组5000，打乱每组顺序）
            ports_low = list(range(10000, 65535 + 1))
            random.shuffle(ports_low)  # 整体打乱低速段端口顺序
            for i in range(0, len(ports_low), 5000):
                port_group = ports_low[i:i + 5000]
                executor.submit(self.scan_random_ports, port_group, "low")
            # 中速段：1~3000（分组1000，打乱每组顺序）
            ports_mid = list(range(1, 3000 + 1))
            random.shuffle(ports_mid)  # 整体打乱中速段端口顺序
            for i in range(0, len(ports_mid), 1000):
                port_group = ports_mid[i:i + 1000]
                executor.submit(self.scan_random_ports, port_group, "mid")
            # 高速段：3000~10000（分组500，打乱每组顺序）
            ports_high = list(range(3000, 10000 + 1))
            random.shuffle(ports_high)  # 整体打乱高速段端口顺序
            for i in range(0, len(ports_high), 500):
                port_group = ports_high[i:i + 500]
                executor.submit(self.scan_random_ports, port_group, "high")

    def scan_priority_ports(self):
        """专门扫描“原有端口”（port_list2），第一优先级，每次轮次优先完整遍历"""
        while True:
            # 每次扫描前打乱port_list2顺序，避免固定顺序
            with self.lock:
                priority_ports = self.port_list2.copy()
            random.shuffle(priority_ports)

            # 遍历扫描所有原有端口
            for port in priority_ports:
                while not self.mode:
                    time.sleep(1)
                if not (0 <= port <= 65535):
                    continue

                # 避免10秒内重复扫描
                current_time = time.time()
                if port in self.last_scan_time and current_time - self.last_scan_time[port] < 10:
                    continue

                # 扫描并更新数据（加锁保护）
                is_open, service_type = scan_port(self.ip, port)
                with self.lock:
                    self.last_scan_time[port] = current_time
                    if is_open:
                        self.port_list[port] = service_type
                    elif port in self.port_list:
                        del self.port_list[port]
            # 原有端口扫描一轮后，休眠（与其他端口轮次间隔一致）
            time.sleep(self.scan_interval)

    def scan_random_ports(self, port_group, speed_level):
        """扫描“其他端口段”（随机顺序），第二优先级，配合轮次控制"""
        for _ in range(self.scan_rounds):
            # 每次轮次前再次打乱当前端口组顺序，确保随机化
            random.shuffle(port_group)
            for port in port_group:
                while not self.mode:
                    time.sleep(1)
                if not (0 <= port <= 65535):
                    continue

                # 避免10秒内重复扫描
                current_time = time.time()
                if port in self.last_scan_time and current_time - self.last_scan_time[port] < 10:
                    continue

                # 扫描并更新数据（加锁保护，若发现新端口则加入port_list2）
                is_open, service_type = scan_port(self.ip, port)
                with self.lock:
                    self.last_scan_time[port] = current_time
                    if is_open:
                        self.port_list[port] = service_type
                        # 新端口加入原有端口列表（超限时移除最旧）
                        if port not in self.port_list2:
                            if len(self.port_list2) >= self.max_port_list2_len:
                                self.port_list2.pop(0)
                            self.port_list2.append(port)
                    elif port in self.port_list:
                        del self.port_list[port]
            # 端口组扫描一轮后休眠
            time.sleep(self.scan_interval)

    def save(self):
        # 数据存储逻辑不变（仅在port_list2变化时写入）
        while True:
            with self.lock:
                current_port_list2 = self.port_list2.copy()
            if current_port_list2 and current_port_list2 != self.last_saved_port_list2:
                try:
                    with open('devices/' + self.name, 'w') as f:
                        json.dump(current_port_list2, f)
                    self.last_saved_port_list2 = current_port_list2
                except Exception:
                    pass
            time.sleep(1)