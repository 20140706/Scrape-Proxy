#!/usr/bin/env python3
"""
GitHub Actions SOCKS5代理测试工具 - 修复版
"""

import requests
import random
import os
import sys
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import logging

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('proxy_test.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# 代理来源
PROXY_SOURCES = [
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies_anonymous/socks5.txt",
    "https://raw.githubusercontent.com/ErcinDedeoglu/proxies/main/proxies/socks5.txt",
    "https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/socks5.txt",
]

# 测试网站
TEST_WEBSITES = [
    "https://icanhazip.com",
    "https://api.ipify.org",
]

class ProxyTester:
    def __init__(self, max_workers=10, timeout=8):
        self.max_workers = max_workers
        self.timeout = timeout
        self.session = requests.Session()
        
    def fetch_proxies(self):
        """获取代理列表"""
        all_proxies = []
        for url in PROXY_SOURCES:
            try:
                response = self.session.get(url, timeout=10)
                if response.status_code == 200:
                    proxies = [line.strip() for line in response.text.split('\n') 
                              if line.strip() and ':' in line and not line.startswith('#')]
                    all_proxies.extend(proxies)
                    logger.info(f"从 {url} 获取到 {len(proxies)} 个代理")
            except Exception as e:
                logger.warning(f"获取 {url} 失败: {e}")
        
        return list(set(all_proxies))
    
    def test_proxy(self, proxy):
        """测试单个代理"""
        try:
            proxy_url = f"socks5://{proxy}"
            proxies = {'http': proxy_url, 'https': proxy_url}
            
            results = []
            for website in TEST_WEBSITES:
                start_time = time.time()
                response = self.session.get(website, proxies=proxies, timeout=self.timeout)
                latency = time.time() - start_time
                
                if response.status_code == 200:
                    results.append({
                        'proxy': proxy,
                        'website': website,
                        'status_code': response.status_code,
                        'ip': response.text.strip(),
                        'latency': round(latency, 2),
                        'success': True
                    })
            
            return results if len(results) == len(TEST_WEBSITES) else None
            
        except Exception as e:
            return None
    
    def test_proxies(self, proxies, max_tests=50):
        """批量测试代理"""
        working_proxies = []
        results = []
        
        test_proxies = proxies[:max_tests]
        logger.info(f"开始测试 {len(test_proxies)} 个代理")
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_proxy = {executor.submit(self.test_proxy, proxy): proxy 
                              for proxy in test_proxies}
            
            for future in as_completed(future_to_proxy):
                proxy = future_to_proxy[future]
                try:
                    proxy_results = future.result()
                    if proxy_results:
                        working_proxies.append(proxy)
                        results.extend(proxy_results)
                        logger.info(f"✓ {proxy} 可用")
                except Exception:
                    pass
        
        return results, working_proxies
    
    def save_results(self, results, working_proxies, total_count):
        """保存结果"""
        # 保存详细结果
        with open('proxy_results.json', 'w', encoding='utf-8') as f:
            json.dump({
                'test_time': datetime.now().isoformat(),
                'total_proxies': total_count,
                'working_proxies': len(working_proxies),
                'results': results
            }, f, indent=2, ensure_ascii=False)
        
        # 保存可用代理列表
        with open('available_proxies.txt', 'w', encoding='utf-8') as f:
            f.write(f"# 生成时间: {datetime.now()}\n")
            f.write(f"# 总代理数: {total_count}\n")
            f.write(f"# 可用代理数: {len(working_proxies)}\n\n")
            f.write('\n'.join(working_proxies))
        
        # 保存最佳代理
        if results:
            best = min(results, key=lambda x: x['latency'])
            with open('BEST_SOCKS5.txt', 'w') as f:
                f.write(best['proxy'])
    
    def run(self):
        """主运行函数"""
        logger.info("🚀 开始代理测试")
        
        # 获取代理
        proxies = self.fetch_proxies()
        if not proxies:
            logger.error("❌ 未获取到代理")
            return
        
        logger.info(f"📊 获取到 {len(proxies)} 个代理")
        
        # 测试代理
        results, working_proxies = self.test_proxies(proxies)
        
        # 保存结果
        if working_proxies:
            self.save_results(results, working_proxies, len(proxies))
            logger.info(f"✅ 测试完成，找到 {len(working_proxies)} 个可用代理")
            
            # 生成简单的HTML报告
            self.generate_html_report(results, len(proxies))
        else:
            logger.warning("⚠️ 未找到可用代理")
    
    def generate_html_report(self, results, total_count):
        """生成HTML报告"""
        working_count = len(set(r['proxy'] for r in results))
        
        html = f"""
        <html>
        <head><title>代理测试报告</title></head>
        <body>
            <h1>代理测试报告</h1>
            <p>测试时间: {datetime.now()}</p>
            <p>总代理数: {total_count}</p>
            <p>可用代理数: {working_count}</p>
            <h2>可用代理列表</h2>
            <ul>
        """
        
        for proxy in set(r['proxy'] for r in results):
            proxy_results = [r for r in results if r['proxy'] == proxy]
            avg_latency = sum(r['latency'] for r in proxy_results) / len(proxy_results)
            html += f'<li>{proxy} (平均延迟: {avg_latency:.2f}s)</li>'
        
        html += "</ul></body></html>"
        
        with open('proxy_report.html', 'w', encoding='utf-8') as f:
            f.write(html)

def main():
    tester = ProxyTester()
    tester.run()

if __name__ == "__main__":
    main()
