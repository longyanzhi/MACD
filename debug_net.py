import os
import requests

# 检查 Python 环境中的代理变量
print("HTTP_PROXY:", os.environ.get('HTTP_PROXY'))
print("HTTPS_PROXY:", os.environ.get('HTTPS_PROXY'))
print("http_proxy:", os.environ.get('http_proxy'))
print("https_proxy:", os.environ.get('https_proxy'))

# 检查 requests 库的默认代理
print("Requests default proxies:", requests.utils.get_environ_proxies('https://push2his.eastmoney.com'))