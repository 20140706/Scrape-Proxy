#!/usr/bin/env python3
"""
GitHub Actions SOCKS5代理测试工具 - 简化版（无HTML报告）
"""

import requests
import random
import os
import sys
import time
from datetime import datetime
import json
import logging

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

# 代理来源列表
PROXY_SOURCES = [
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies_anonymous/socks5.txt",
    "https://raw.githubusercontent.com/ErcinDedeoglu/proxies/main/proxies/socks5.txt",
    "https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/socks5.txt"
]

# 测试网站
TEST_WEBSITES = [
    "https://icanhazip.com",
    "https://api.ipify.org"
]

# User-Agent列表
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
]

def get_user_agent():
    """获取随机User-Agent"""
    return random.choice(USER_AGENTS)

def fetch_proxies():
    """从多个来源获取代理"""
    all_proxies = set()
    
    for url in PROXY_SOURCES:
        try:
            logger.info(f"正在获取代理: {url}")
            response = requests.get(url, timeout=10, headers={'User-Agent': get_user_agent()})
            response.raise_for_status()
            
            proxies = response.text.strip().split('\n')
            valid_proxies = [p.strip() for p in proxies if p.strip() and ':' in p and not p.startswith('#')]
            
            logger.info(f"从 {url} 获取到 {len(valid_proxies)} 个代理")
            all_proxies.update(valid_proxies)
            
        except Exception as e:
            logger.warning(f"获取 {url} 失败: {e}")
    
    proxy_list = list(all_proxies)
    logger.info(f"总共获取到 {len(proxy_list)} 个唯一代理")
    return proxy_list

def test_single_proxy(proxy, timeout=8):
    """测试单个代理"""
    try:
        proxy_dict = {
            'http': f'socks5://{proxy}',
            'https': f'socks5://{proxy}'
        }
        
        results = []
        
        for website in TEST_WEBSITES:
            try:
                start_time = time.time()
                response = requests.get(
                    website, 
                    proxies=proxy_dict, 
                    timeout=timeout,
                    headers={'User-Agent': get_user_agent()}
                )
                latency = time.time() - start_time
                
                if response.status_code == 200:
                    results.append({
                        'website': website,
                        'status_code': response.status_code,
                        'response': response.text.strip(),
                        'latency': round(latency, 2)
                    })
                else:
                    logger.debug(f"代理 {proxy} 在 {website} 返回状态码 {response.status_code}")
                    return None
                    
            except Exception as e:
                logger.debug(f"代理 {proxy} 在 {website} 测试失败: {e}")
                return None
        
        # 如果所有网站测试都通过
        avg_latency = sum(r['latency'] for r in results) / len(results)
        return {
            'proxy': proxy,
            'avg_latency': avg_latency,
            'results': results,
            'success': True
        }
        
    except Exception as e:
        logger.debug(f"代理 {proxy} 测试失败: {e}")
        return None

def test_proxies(proxy_list, max_proxies_to_test=30):
    """测试代理列表"""
    working_proxies = []
    tested_count = 0
    
    # 打乱代理列表
    random.shuffle(proxy_list)
    
    # 限制测试数量
    proxies_to_test = proxy_list[:max_proxies_to_test]
    logger.info(f"将测试 {len(proxies_to_test)} 个代理")
    
    for proxy in proxies_to_test:
        tested_count += 1
        
        if tested_count % 5 == 0:
            logger.info(f"已测试 {tested_count}/{len(proxies_to_test)} 个代理，找到 {len(working_proxies)} 个可用")
        
        result = test_single_proxy(proxy)
        if result:
            working_proxies.append(result)
            logger.info(f"✓ 找到可用代理: {proxy} (延迟: {result['avg_latency']}秒)")
            
            # 如果已经找到足够多的代理，可以提前停止
            if len(working_proxies) >= 5:
                logger.info(f"已找到 {len(working_proxies)} 个可用代理，提前停止测试")
                break
    
    return working_proxies

def save_results(working_proxies, total_proxies_fetched):
    """保存结果到文件"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # 1. 保存JSON格式的详细结果
    json_data = {
        'timestamp': timestamp,
        'total_proxies_fetched': total_proxies_fetched,
        'working_proxies_count': len(working_proxies),
        'working_proxies': working_proxies
    }
    
    with open('proxy_results.json', 'w', encoding='utf-8') as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)
    
    # 2. 保存纯文本代理列表 - 即使没有可用代理也创建文件
    with open('available_proxies.txt', 'w', encoding='utf-8') as f:
        f.write(f"# 生成时间: {timestamp}\n")
        f.write(f"# 总代理数: {total_proxies_fetched}\n")
        f.write(f"# 可用代理数: {len(working_proxies)}\n")
        f.write("# 格式: IP:端口\n\n")
        
        if working_proxies:
            for proxy_info in working_proxies:
                f.write(f"{proxy_info['proxy']}\n")
        else:
            f.write("# 本次测试未找到可用代理\n")
    
    # 3. 保存最佳代理 - 即使没有可用代理也创建文件
    with open('BEST_SOCKS5.txt', 'w', encoding='utf-8') as f:
        if working_proxies:
            best_proxy = min(working_proxies, key=lambda x: x['avg_latency'])
            f.write(best_proxy['proxy'])
            logger.info(f"最佳代理: {best_proxy['proxy']} (延迟: {best_proxy['avg_latency']}秒)")
        else:
            f.write("# 本次测试未找到可用代理\n")
    
    logger.info(f"结果已保存到文件")

def main():
    """主函数"""
    logger.info("🚀 开始SOCKS5代理测试")
    start_time = time.time()
    
    try:
        # 1. 获取代理列表
        logger.info("📡 正在从多个来源获取代理...")
        all_proxies = fetch_proxies()
        
        if not all_proxies:
            logger.error("❌ 未能获取到任何代理")
            # 创建空的结果文件
            save_results([], 0)
            return 0
        
        # 2. 测试代理
        logger.info("🧪 开始测试代理...")
        working_proxies = test_proxies(all_proxies)
        
        # 3. 保存结果
        logger.info("💾 保存测试结果...")
        save_results(working_proxies, len(all_proxies))
        
        # 4. 显示统计信息
        end_time = time.time()
        total_time = end_time - start_time
        
        print("\n" + "="*60)
        print("🎯 SOCKS5代理测试完成")
        print("="*60)
        print(f"总代理数: {len(all_proxies)}")
        print(f"可用代理数: {len(working_proxies)}")
        print(f"测试耗时: {total_time:.2f}秒")
        
        if working_proxies:
            best_proxy = min(working_proxies, key=lambda x: x['avg_latency'])
            print(f"最佳代理: {best_proxy['proxy']} (延迟: {best_proxy['avg_latency']:.2f}秒)")
        else:
            print("❌ 未找到可用代理")
        
        print("="*60)
        print("📁 生成的文件:")
        print("  - available_proxies.txt (可用代理列表)")
        print("  - BEST_SOCKS5.txt (最佳代理)")
        print("  - proxy_results.json (完整结果)")
        print("  - proxy_test.log (日志文件)")
        print("="*60)
        
        return 0
        
    except KeyboardInterrupt:
        logger.info("测试被用户中断")
        return 130
    except Exception as e:
        logger.error(f"测试过程中发生错误: {e}")
        # 即使出错也创建结果文件
        save_results([], 0)
        return 1

if __name__ == "__main__":
    sys.exit(main())
