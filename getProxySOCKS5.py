#!/usr/bin/env python3
"""
GitHub Actions SOCKS5代理测试工具
自动从多个来源获取代理，测试可用性，并保存结果
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
from typing import List, Dict, Optional, Tuple

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
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt",
    "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt",
    "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/socks5.txt"
]

# 测试网站
TEST_WEBSITES = [
    "https://icanhazip.com",  # 返回IP
    "https://api.ipify.org",   # 返回IP
    "http://httpbin.org/ip",   # 返回JSON格式IP
]

# User-Agent列表
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
]

class ProxyTester:
    """SOCKS5代理测试器"""
    
    def __init__(self, max_workers: int = 20, timeout: int = 10):
        """
        初始化代理测试器
        
        Args:
            max_workers: 最大线程数
            timeout: 请求超时时间（秒）
        """
        self.max_workers = max_workers
        self.timeout = timeout
        self.session = requests.Session()
        self.results = []
        self.working_proxies = []
        
    def get_proxy_sources(self) -> List[str]:
        """获取代理来源列表"""
        return PROXY_SOURCES
    
    def fetch_proxies_from_source(self, url: str) -> List[str]:
        """从单个来源获取代理"""
        try:
            headers = {'User-Agent': random.choice(USER_AGENTS)}
            response = self.session.get(url, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            
            # 解析代理列表
            proxies = []
            for line in response.text.splitlines():
                line = line.strip()
                if line and not line.startswith('#'):
                    # 清理代理格式
                    proxy = line.split()[0] if ' ' in line else line
                    if ':' in proxy:
                        proxies.append(proxy)
            
            logger.info(f"从 {url} 获取到 {len(proxies)} 个代理")
            return proxies
        except Exception as e:
            logger.warning(f"从 {url} 获取代理失败: {str(e)}")
            return []
    
    def fetch_all_proxies(self) -> List[str]:
        """从所有来源获取代理"""
        all_proxies = []
        
        logger.info(f"开始从 {len(PROXY_SOURCES)} 个来源获取代理...")
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(self.fetch_proxies_from_source, url): url 
                      for url in self.get_proxy_sources()}
            
            for future in as_completed(futures):
                url = futures[future]
                try:
                    proxies = future.result()
                    all_proxies.extend(proxies)
                except Exception as e:
                    logger.error(f"处理 {url} 时出错: {str(e)}")
        
        # 去重
        unique_proxies = list(set(all_proxies))
        logger.info(f"获取到 {len(unique_proxies)} 个唯一代理")
        
        return unique_proxies
    
    def test_single_proxy(self, proxy: str, website: str) -> Optional[Dict]:
        """测试单个代理在单个网站上的可用性"""
        try:
            # 解析代理
            if '://' in proxy:
                proxy_url = proxy
            else:
                proxy_url = f"socks5://{proxy}"
            
            # 准备请求
            headers = {
                'User-Agent': random.choice(USER_AGENTS),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
            
            proxies = {
                'http': proxy_url,
                'https': proxy_url
            }
            
            # 发送请求
            start_time = time.time()
            response = self.session.get(
                website, 
                proxies=proxies, 
                headers=headers, 
                timeout=self.timeout,
                allow_redirects=True
            )
            latency = time.time() - start_time
            
            response.raise_for_status()
            
            # 解析响应
            if response.status_code == 200:
                # 获取返回的IP
                if 'json' in response.headers.get('Content-Type', ''):
                    ip_data = response.json()
                    if 'ip' in ip_data:
                        returned_ip = ip_data['ip']
                    elif 'origin' in ip_data:
                        returned_ip = ip_data['origin']
                    else:
                        returned_ip = response.text.strip()
                else:
                    returned_ip = response.text.strip()
                
                return {
                    'proxy': proxy,
                    'website': website,
                    'status_code': response.status_code,
                    'ip': returned_ip,
                    'latency': round(latency, 2),
                    'success': True
                }
            
        except requests.exceptions.Timeout:
            logger.debug(f"代理 {proxy} 在 {website} 上超时")
        except requests.exceptions.ProxyError as e:
            logger.debug(f"代理 {proxy} 连接失败: {str(e)}")
        except requests.exceptions.ConnectionError as e:
            logger.debug(f"代理 {proxy} 连接错误: {str(e)}")
        except requests.exceptions.RequestException as e:
            logger.debug(f"代理 {proxy} 请求异常: {str(e)}")
        except Exception as e:
            logger.debug(f"测试代理 {proxy} 时发生未知错误: {str(e)}")
        
        return None
    
    def test_proxy_on_all_sites(self, proxy: str) -> List[Dict]:
        """测试代理在所有网站上的表现"""
        proxy_results = []
        
        for website in TEST_WEBSITES:
            result = self.test_single_proxy(proxy, website)
            if result:
                proxy_results.append(result)
            else:
                # 任意一个网站失败，则认为代理不可用
                return []
        
        return proxy_results
    
    def test_proxies_batch(self, proxies: List[str], max_tests: int = 50) -> Tuple[List[Dict], List[str]]:
        """
        批量测试代理
        
        Args:
            proxies: 代理列表
            max_tests: 最大测试数量
            
        Returns:
            Tuple[测试结果列表, 可用代理列表]
        """
        all_results = []
        working_proxies = []
        
        # 限制测试数量
        test_proxies = proxies[:max_tests] if len(proxies) > max_tests else proxies
        logger.info(f"开始测试 {len(test_proxies)} 个代理...")
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_proxy = {executor.submit(self.test_proxy_on_all_sites, proxy): proxy 
                              for proxy in test_proxies}
            
            for i, future in enumerate(as_completed(future_to_proxy), 1):
                proxy = future_to_proxy[future]
                
                if i % 10 == 0:
                    logger.info(f"已测试 {i}/{len(test_proxies)} 个代理，找到 {len(working_proxies)} 个可用代理")
                
                try:
                    results = future.result(timeout=self.timeout + 5)
                    if results:
                        all_results.extend(results)
                        working_proxies.append(proxy)
                        logger.info(f"✓ 代理 {proxy} 可用 (延迟: {results[0]['latency']}秒)")
                except Exception as e:
                    logger.debug(f"测试代理 {proxy} 时出错: {str(e)}")
        
        logger.info(f"测试完成。共找到 {len(working_proxies)} 个可用代理")
        return all_results, working_proxies
    
    def save_results(self, results: List[Dict], working_proxies: List[str], 
                    all_proxies_count: int) -> None:
        """保存测试结果到文件"""
        
        # 1. 保存详细结果到JSON文件
        detailed_results = {
            'test_time': datetime.now().isoformat(),
            'total_proxies_fetched': all_proxies_count,
            'total_proxies_tested': len(set(r['proxy'] for r in results)),
            'working_proxies_count': len(working_proxies),
            'test_websites': TEST_WEBSITES,
            'results': results
        }
        
        with open('proxy_results.json', 'w', encoding='utf-8') as f:
            json.dump(detailed_results, f, indent=2, ensure_ascii=False)
        
        # 2. 保存可用的代理列表到文本文件
        with open('available_proxies.txt', 'w', encoding='utf-8') as f:
            f.write(f"# 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# 总代理数: {all_proxies_count}\n")
            f.write(f"# 可用代理数: {len(working_proxies)}\n")
            f.write("# 格式: IP:端口\n")
            f.write("\n".join(working_proxies))
        
        # 3. 保存单个最佳代理（延迟最低的）
        if working_proxies and results:
            # 按延迟排序
            sorted_results = sorted(results, key=lambda x: x['latency'])
            best_proxy = sorted_results[0]['proxy']
            
            with open('BEST_SOCKS5.txt', 'w', encoding='utf-8') as f:
                f.write(best_proxy)
            
            logger.info(f"最佳代理已保存: {best_proxy}")
        
        # 4. 生成HTML报告
        self.generate_html_report(detailed_results)
    
    def generate_html_report(self, data: Dict) -> None:
        """生成HTML格式的报告"""
        html = f"""
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>SOCKS5代理测试报告</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }}
                .summary {{ background: #f5f5f5; padding: 20px; border-radius: 5px; margin-bottom: 20px; }}
                .summary h2 {{ margin-top: 0; }}
                .stat {{ display: inline-block; margin-right: 20px; background: white; padding: 10px; border-radius: 3px; }}
                .proxy-list {{ background: #e8f4f8; padding: 15px; border-radius: 5px; }}
                .proxy-item {{ 
                    background: white; 
                    margin: 5px 0; 
                    padding: 10px; 
                    border-left: 4px solid #4CAF50;
                    border-radius: 3px;
                }}
                .latency {{ color: #666; font-size: 0.9em; }}
                .good {{ color: #4CAF50; }}
                .medium {{ color: #FF9800; }}
                .poor {{ color: #F44336; }}
                table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #f2f2f2; }}
            </style>
        </head>
        <body>
            <h1>📡 SOCKS5代理测试报告</h1>
            
            <div class="summary">
                <h2>📊 测试概览</h2>
                <div class="stat">总获取代理数: {data['total_proxies_fetched']}</div>
                <div class="stat">测试代理数: {data['total_proxies_tested']}</div>
                <div class="stat">可用代理数: <span class="good">{data['working_proxies_count']}</span></div>
                <div class="stat">测试时间: {data['test_time']}</div>
            </div>
            
            <h2>✅ 可用代理列表</h2>
        """
        
        if data['results']:
            # 按代理分组
            proxy_groups = {}
            for result in data['results']:
                proxy = result['proxy']
                if proxy not in proxy_groups:
                    proxy_groups[proxy] = []
                proxy_groups[proxy].append(result)
            
            # 计算每个代理的平均延迟
            proxy_stats = []
            for proxy, results in proxy_groups.items():
                avg_latency = sum(r['latency'] for r in results) / len(results)
                proxy_stats.append({
                    'proxy': proxy,
                    'avg_latency': avg_latency,
                    'success_rate': 100 * len(results) / len(TEST_WEBSITES)
                })
            
            # 按延迟排序
            proxy_stats.sort(key=lambda x: x['avg_latency'])
            
            html += "<table>"
            html += "<tr><th>排名</th><th>代理</th><th>平均延迟(秒)</th><th>成功率</th><th>状态</th></tr>"
            
            for i, stat in enumerate(proxy_stats, 1):
                latency_class = "good" if stat['avg_latency'] < 2 else "medium" if stat['avg_latency'] < 5 else "poor"
                html += f"""
                <tr>
                    <td>#{i}</td>
                    <td>{stat['proxy']}</td>
                    <td class="{latency_class}">{stat['avg_latency']:.2f}</td>
                    <td>{stat['success_rate']:.1f}%</td>
                    <td class="good">✓ 可用</td>
                </tr>
                """
            
            html += "</table>"
            
            # 添加前5个代理的详细信息
            html += "<h3>🏆 最佳代理详情</h3>"
            for i, stat in enumerate(proxy_stats[:5], 1):
                html += f"""
                <div class="proxy-item">
                    <strong>#{i}: {stat['proxy']}</strong>
                    <div class="latency">平均延迟: {stat['avg_latency']:.2f}秒</div>
                </div>
                """
        else:
            html += "<p>❌ 未找到可用代理</p>"
        
        html += f"""
            <hr>
            <footer>
                <p><small>测试网站: {', '.join(TEST_WEBSITES)}</small></p>
                <p><small>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</small></p>
            </footer>
        </body>
        </html>
        """
        
        with open('proxy_report.html', 'w', encoding='utf-8') as f:
            f.write(html)
    
    def load_previous_best_proxy(self) -> Optional[str]:
        """加载之前保存的最佳代理"""
        if os.path.exists('BEST_SOCKS5.txt'):
            try:
                with open('BEST_SOCKS5.txt', 'r') as f:
                    proxy = f.read().strip()
                    if proxy and ':' in proxy:
                        logger.info(f"加载之前的最佳代理: {proxy}")
                        return proxy
            except Exception as e:
                logger.warning(f"加载之前的最佳代理失败: {str(e)}")
        return None
    
    def run(self) -> None:
        """主运行函数"""
        logger.info("🚀 开始SOCKS5代理测试")
        start_time = datetime.now()
        
        try:
            # 1. 尝试先测试之前的最佳代理
            previous_best = self.load_previous_best_proxy()
            if previous_best:
                logger.info(f"测试之前的最佳代理: {previous_best}")
                test_result = self.test_proxy_on_all_sites(previous_best)
                if test_result:
                    logger.info(f"✅ 之前的最佳代理仍然可用: {previous_best}")
                    self.working_proxies = [previous_best]
                    self.results = test_result
                    
                    # 保存结果
                    self.save_results(test_result, [previous_best], 1)
                    
                    end_time = datetime.now()
                    logger.info(f"✅ 测试完成 (耗时: {(end_time - start_time).total_seconds():.1f}秒)")
                    logger.info(f"✅ 之前的最佳代理仍然可用，无需重新测试所有代理")
                    return
            
            # 2. 获取所有代理
            all_proxies = self.fetch_all_proxies()
            
            if not all_proxies:
                logger.error("❌ 未能获取到任何代理")
                return
            
            # 3. 随机打乱代理列表
            random.shuffle(all_proxies)
            
            # 4. 批量测试代理
            results, working_proxies = self.test_proxies_batch(all_proxies, max_tests=100)
            
            # 5. 保存结果
            if results and working_proxies:
                self.save_results(results, working_proxies, len(all_proxies))
                
                # 显示最佳代理
                best_proxy = min(results, key=lambda x: x['latency'])
                logger.info(f"🏆 最佳代理: {best_proxy['proxy']} (延迟: {best_proxy['latency']}秒)")
            else:
                logger.warning("⚠️ 未找到任何可用代理")
                # 保存空结果
                with open('available_proxies.txt', 'w', encoding='utf-8') as f:
                    f.write("# 未找到可用代理\n")
            
            end_time = datetime.now()
            logger.info(f"✅ 测试完成 (耗时: {(end_time - start_time).total_seconds():.1f}秒)")
            
        except Exception as e:
            logger.error(f"❌ 测试过程中发生错误: {str(e)}", exc_info=True)
            raise

def main():
    """程序入口点"""
    try:
        # 创建测试器实例
        tester = ProxyTester(max_workers=15, timeout=8)
        
        # 运行测试
        tester.run()
        
        # 打印总结
        print("\n" + "="*60)
        print("🎯 SOCKS5代理测试总结")
        print("="*60)
        
        if os.path.exists('available_proxies.txt'):
            with open('available_proxies.txt', 'r', encoding='utf-8') as f:
                lines = f.readlines()
                if len(lines) > 3:  # 跳过注释行
                    print(f"✅ 找到 {len(lines)-3} 个可用代理")
                    print(f"📁 结果文件: available_proxies.txt, proxy_results.json, proxy_report.html")
                    print(f"🏆 最佳代理: {open('BEST_SOCKS5.txt').read().strip() if os.path.exists('BEST_SOCKS5.txt') else '无'}")
                else:
                    print("❌ 未找到可用代理")
        
        print("="*60)
        
    except KeyboardInterrupt:
        logger.info("测试被用户中断")
        sys.exit(1)
    except Exception as e:
        logger.error(f"程序执行失败: {str(e)}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
