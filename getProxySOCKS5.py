#!/usr/bin/env python3
"""
GitHub Actions SOCKS5代理测试工具 - 多线程完整版
修复版：正确的SOCKS5代理验证
"""

import requests
import random
import sys
import time
from datetime import datetime
import json
import logging
import ipaddress
from concurrent.futures import ThreadPoolExecutor, as_completed


# 尝试安装必要的库
def install_dependencies():
    try:
        import socket
        return True
    except ImportError:
        return False


# 配置日志
def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('proxy_test.log', encoding='utf-8')
        ]
    )
    return logging.getLogger(__name__)


logger = setup_logging()

# 全局变量：本机真实公网 IP
REAL_IP = None


def get_real_ip():
    """获取本机真实公网 IP（用于对比验证）"""
    global REAL_IP
    if REAL_IP is not None:
        return REAL_IP
    try:
        resp = requests.get("https://icanhazip.com", timeout=10)
        ip = resp.text.strip()
        if is_valid_ipv4(ip):
            REAL_IP = ip
            logger.info(f"本机真实公网 IP: {REAL_IP}")
            return REAL_IP
        else:
            logger.error("响应内容不是有效 IPv4 地址")
            return None
    except Exception as e:
        logger.error(f"获取本机公网 IP 失败: {e}")
        return None


def is_valid_ipv4(ip_str):
    """严格校验 IPv4 地址"""
    try:
        ipaddress.IPv4Address(ip_str)
        return True
    except ipaddress.AddressValueError:
        return False


# 代理来源列表
PROXY_SOURCES = [
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies_anonymous/socks5.txt",
    "https://raw.githubusercontent.com/ErcinDedeoglu/proxies/main/proxies/socks5.txt",
    "https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/socks5.txt"
]

# 测试网站
TEST_WEBSITE = "https://icanhazip.com"

# User-Agent列表
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
]


def get_user_agent():
    """获取随机User-Agent"""
    return random.choice(USER_AGENTS)


def parse_proxy(proxy_str):
    """解析代理字符串，支持格式: ip:port 或 user:pass@ip:port"""
    proxy_str = proxy_str.strip()

    # 移除可能的协议前缀
    for prefix in ['socks5://', 'socks4://', 'http://', 'https://']:
        if proxy_str.startswith(prefix):
            proxy_str = proxy_str[len(prefix):]

    # 分离认证信息和主机信息
    if '@' in proxy_str:
        auth_part, host_part = proxy_str.split('@', 1)
        if ':' in auth_part:
            username, password = auth_part.split(':', 1)
        else:
            username, password = auth_part, None
    else:
        username, password = None, None
        host_part = proxy_str

    # 解析主机和端口
    if ':' in host_part:
        host, port_str = host_part.rsplit(':', 1)
        try:
            port = int(port_str)
        except ValueError:
            port = 1080
    else:
        host, port = host_part, 1080

    return {
        'host': host.strip(),
        'port': port,
        'username': username,
        'password': password,
        'original': proxy_str.strip()
    }


def test_single_proxy(proxy_str, timeout=8, real_ip=None):
    """测试单个SOCKS5代理"""
    try:
        # 解析代理
        proxy_info = parse_proxy(proxy_str)

        # 构造代理字典
        proxy_url = f"socks5://{proxy_info['original']}"

        # 设置代理
        proxies = {
            'http': proxy_url,
            'https': proxy_url
        }

        # 使用代理测试连接
        start_time = time.time()
        response = requests.get(
            TEST_WEBSITE,
            proxies=proxies,
            timeout=timeout,
            headers={'User-Agent': get_user_agent()},
            allow_redirects=False
        )
        latency = time.time() - start_time

        if response.status_code == 200:
            ip = response.text.strip()

            # 验证IP格式
            if not is_valid_ipv4(ip):
                logger.debug(f"代理 {proxy_str} 返回无效IP格式: {repr(ip)}")
                return None

            # 检查是否与真实IP相同
            if real_ip and ip == real_ip:
                logger.debug(f"代理 {proxy_str} 返回与本机相同的IP ({ip})，判定无效")
                return None

            logger.debug(f"✓ 代理 {proxy_str} 测试成功: {ip} (延迟: {latency:.2f}s)")

            return {
                'proxy': proxy_str,
                'ip': ip,
                'avg_latency': round(latency, 2),
                'results': [{
                    'website': TEST_WEBSITE,
                    'status_code': 200,
                    'response': ip,
                    'latency': round(latency, 2)
                }],
                'success': True
            }
        else:
            logger.debug(f"代理 {proxy_str} 返回状态码: {response.status_code}")

    except requests.exceptions.ConnectTimeout:
        logger.debug(f"代理 {proxy_str} 连接超时")
    except requests.exceptions.ReadTimeout:
        logger.debug(f"代理 {proxy_str} 读取超时")
    except requests.exceptions.ConnectionError as e:
        logger.debug(f"代理 {proxy_str} 连接错误: {e}")
    except requests.exceptions.ProxyError as e:
        logger.debug(f"代理 {proxy_str} 代理错误: {e}")
    except Exception as e:
        logger.debug(f"代理 {proxy_str} 测试失败: {type(e).__name__}")

    return None


def test_proxies(proxy_list, real_ip=None, max_workers=500):
    """使用多线程测试所有代理"""
    if not proxy_list:
        return []

    logger.info(f"启动 {max_workers} 个线程，开始测试全部 {len(proxy_list)} 个代理...")
    random.shuffle(proxy_list)  # 打乱顺序

    working_proxies = []
    tested_count = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有任务
        future_to_proxy = {executor.submit(test_single_proxy, proxy, 8, real_ip): proxy for proxy in proxy_list}

        # 处理完成的任务
        for future in as_completed(future_to_proxy):
            tested_count += 1
            proxy = future_to_proxy[future]

            try:
                result = future.result(timeout=10)
                if result:
                    working_proxies.append(result)
                    logger.info(
                        f"✓ 可用代理 [{len(working_proxies)}]: {result['proxy']} "
                        f"(出口IP: {result['ip']}, 延迟: {result['avg_latency']}s)"
                    )
            except Exception as e:
                logger.debug(f"测试代理 {proxy} 时发生异常: {e}")

            # 每完成10%或每100个打印一次进度
            if tested_count % 100 == 0 or tested_count == len(proxy_list):
                logger.info(
                    f"进度: 已测试 {tested_count}/{len(proxy_list)} 个代理，找到 {len(working_proxies)} 个可用代理")

    logger.info(f"✅ 多线程测试完成！共找到 {len(working_proxies)} 个可用代理")
    return working_proxies


def fetch_proxies():
    """从多个来源获取代理"""
    all_proxies = set()
    failed_sources = 0

    for url in PROXY_SOURCES:
        try:
            logger.info(f"正在获取代理: {url}")
            headers = {
                'User-Agent': get_user_agent(),
                'Accept': 'text/plain,text/html',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive'
            }

            response = requests.get(url, timeout=15, headers=headers)
            response.raise_for_status()

            # 解析代理列表
            lines = response.text.strip().split('\n')
            valid_count = 0

            for line in lines:
                line = line.strip()
                if not line or line.startswith(('#', '//', '/*', '*/', '--')):
                    continue

                # 简单格式验证
                if ':' in line and '.' in line.split(':')[0]:
                    all_proxies.add(line)
                    valid_count += 1

            logger.info(f"从 {url} 获取到 {valid_count} 个代理")

        except requests.exceptions.Timeout:
            logger.warning(f"获取 {url} 超时")
            failed_sources += 1
        except requests.exceptions.RequestException as e:
            logger.warning(f"获取 {url} 失败: {e}")
            failed_sources += 1
        except Exception as e:
            logger.warning(f"处理 {url} 时出错: {e}")
            failed_sources += 1

    proxy_list = list(all_proxies)
    logger.info(f"总共从 {len(PROXY_SOURCES)} 个源获取到 {len(proxy_list)} 个唯一代理 ({failed_sources} 个源失败)")

    return proxy_list


def save_results(working_proxies, total_proxies_fetched):
    """保存结果到文件"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 按延迟排序
    working_proxies.sort(key=lambda x: x['avg_latency'])

    # 保存完整JSON结果
    json_data = {
        'timestamp': timestamp,
        'total_proxies_fetched': total_proxies_fetched,
        'working_proxies_count': len(working_proxies),
        'working_proxies': working_proxies
    }

    with open('proxy_results.json', 'w', encoding='utf-8') as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)

    # 保存所有可用代理
    with open('available_proxies.txt', 'w', encoding='utf-8') as f:
        for proxy_info in working_proxies:
            f.write(f"{proxy_info['proxy']}\n")

    # 保存前20个最快代理
    with open('BEST_SOCKS5.txt', 'w', encoding='utf-8') as f:
        if working_proxies:
            for i, proxy_info in enumerate(working_proxies[:20], 1):
                f.write(f"{proxy_info['proxy']} | 延迟: {proxy_info['avg_latency']}秒 | IP: {proxy_info['ip']}\n")
        else:
            f.write("# 未找到可用代理\n")

    logger.info("💾 结果已保存到: available_proxies.txt, BEST_SOCKS5.txt, proxy_results.json")


def main():
    """主函数"""
    logger.info("🚀 开始 SOCKS5 代理测试（多线程版本）")

    start_time = time.time()

    # 获取本机真实公网 IP
    logger.info("正在获取本机真实公网IP...")
    real_ip = get_real_ip()
    if real_ip is None:
        logger.warning("⚠️ 无法获取本机公网 IP，将跳过 IP 对比验证（可能产生假阳性）")

    try:
        # 1. 获取代理列表
        logger.info("📡 正在从多个来源获取代理...")
        all_proxies = fetch_proxies()

        if not all_proxies:
            logger.error("❌ 未能获取到任何代理")
            save_results([], 0)
            return 0

        logger.info(f"📊 获取到 {len(all_proxies)} 个代理，开始测试...")

        # 2. 多线程测试所有代理
        logger.info("🧪 开始多线程测试所有代理...")
        working_proxies = test_proxies(all_proxies, real_ip=real_ip, max_workers=500)

        # 3. 保存结果
        logger.info("💾 保存测试结果...")
        save_results(working_proxies, len(all_proxies))

        # 4. 显示统计信息
        end_time = time.time()
        total_time = end_time - start_time

        print("\n" + "=" * 60)
        print("🎯 SOCKS5 代理测试完成")
        print("=" * 60)
        print(f"总代理数: {len(all_proxies)}")
        print(f"可用代理数: {len(working_proxies)}")
        print(f"测试耗时: {total_time:.2f} 秒")
        print(f"成功率: {(len(working_proxies) / max(1, len(all_proxies))) * 100:.2f}%")

        if working_proxies:
            print(f"\n🏆 最快的前5个代理:")
            for i, proxy in enumerate(working_proxies[:5], 1):
                print(f"{i:2d}. {proxy['proxy']}")
                print(f"    出口IP: {proxy['ip']}")
                print(f"    延迟: {proxy['avg_latency']}秒")
        else:
            print("❌ 未找到可用代理")

        print("=" * 60)
        print("📁 生成的文件:")
        print("  - available_proxies.txt (所有可用代理)")
        print("  - BEST_SOCKS5.txt (前20个最快代理)")
        print("  - proxy_results.json (完整JSON结果)")
        print("  - proxy_test.log (详细日志)")
        print("=" * 60)

        return 0

    except KeyboardInterrupt:
        logger.info("🛑 测试被用户中断")
        return 130
    except Exception as e:
        logger.exception(f"❌ 测试过程中发生错误: {e}")
        save_results([], 0)
        return 1


if __name__ == "__main__":
    sys.exit(main())
