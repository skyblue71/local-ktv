"""
網路攔截器：擋住所有「連到外面」的連線，只允許連自己這台電腦（127.0.0.1）。
每一次想連到外面，都會被記下來，最後印出報告。

給 check_network.py 和 check_missing_model.py 使用。
注意：一定要在 import 其他程式「之前」呼叫 start()。
"""
import socket

# 自己這台電腦的位址（連這些不算連網）
LOCAL_HOSTS = ["127.0.0.1", "::1", "localhost"]

# 想連到外面的紀錄
outside_attempts = []

# 連到自己電腦的次數（用清單包起來，函式裡面才能修改）
local_count = [0]

# 先把原本的連線功能存起來
_original_connect = socket.socket.connect
_original_getaddrinfo = socket.getaddrinfo


def _get_host(address):
    """從連線位址裡取出主機名稱"""
    if isinstance(address, tuple):
        return str(address[0])
    return str(address)


def _guarded_connect(self, address):
    """替換掉原本的「連線」：連自己電腦就放行，連外面就擋下來"""
    host = _get_host(address)
    if host in LOCAL_HOSTS:
        local_count[0] = local_count[0] + 1
        return _original_connect(self, address)
    outside_attempts.append("連線到 " + str(address))
    raise OSError("測試中：已擋住對外連線")


def _guarded_getaddrinfo(host, *args, **kwargs):
    """替換掉原本的「查網址」：查自己電腦就放行，查外面的網址就擋下來"""
    if host is None or str(host) in LOCAL_HOSTS:
        return _original_getaddrinfo(host, *args, **kwargs)
    outside_attempts.append("查詢網址 " + str(host))
    raise OSError("測試中：已擋住對外連線")


def start():
    """開始攔截"""
    socket.socket.connect = _guarded_connect
    socket.getaddrinfo = _guarded_getaddrinfo
    print("已開始攔截：只允許連到自己這台電腦（127.0.0.1）")


def print_report():
    """印出攔截結果，回傳 True 代表完全沒有連到外面"""
    print()
    print("連到自己電腦的次數：" + str(local_count[0]))
    print("想連到外面的次數：" + str(len(outside_attempts)))
    for item in outside_attempts:
        print("    " + item)
    return len(outside_attempts) == 0
