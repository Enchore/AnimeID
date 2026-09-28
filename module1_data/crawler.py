"""
module1_data/crawler.py - 动漫角色图像数据收集脚本
从动漫论坛、百科网站等渠道收集动漫角色图像

功能：
    - 支持从多个来源下载图像
    - 自动按角色名称分类存储
    - 去重和格式检查
"""
import os
import re
import sys
import time
import hashlib
import requests
import argparse
from pathlib import Path
from urllib.parse import urljoin, urlparse

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import RAW_DIR, ANIME_CHARACTERS, MIN_IMAGES_PER_CLASS

# 请求头模拟浏览器
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


class AnimeImageCrawler:
    """动漫角色图像爬取器"""

    def __init__(self, output_dir: str = RAW_DIR, delay: float = 1.0):
        self.output_dir = output_dir
        self.delay = delay           # 请求间隔（秒），礼貌性爬取
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self._downloaded_hashes = set()  # 用于去重

    def _get_save_dir(self, character_key: str) -> Path:
        """获取角色存储目录"""
        save_dir = Path(self.output_dir) / character_key
        save_dir.mkdir(parents=True, exist_ok=True)
        return save_dir

    def _get_next_index(self, character_key: str) -> int:
        """查找角色的下一个可用文件索引（用于断点续爬）"""
        save_dir = Path(self.output_dir) / character_key
        if not save_dir.exists():
            return 0
        max_idx = -1
        for f in save_dir.iterdir():
            m = re.search(r'_(\d{4})\.(jpg|jpeg|png|gif|webp)$', f.name, re.IGNORECASE)
            if m:
                idx = int(m.group(1))
                if idx > max_idx:
                    max_idx = idx
        return max_idx + 1

    def _compute_hash(self, data: bytes) -> str:
        """计算图像MD5哈希（去重）"""
        return hashlib.md5(data).hexdigest()

    def _is_valid_image(self, data: bytes) -> bool:
        """验证数据是否为有效图像"""
        # JPEG magic bytes
        if data[:2] == b'\xff\xd8':
            return True
        # PNG magic bytes
        if data[:8] == b'\x89PNG\r\n\x1a\n':
            return True
        # GIF magic bytes
        if data[:6] in (b'GIF87a', b'GIF89a'):
            return True
        # WebP
        if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
            return True
        return False

    def _get_extension(self, data: bytes, url: str) -> str:
        """根据数据内容确定文件扩展名"""
        if data[:2] == b'\xff\xd8':
            return '.jpg'
        if data[:8] == b'\x89PNG\r\n\x1a\n':
            return '.png'
        if data[:6] in (b'GIF87a', b'GIF89a'):
            return '.gif'
        if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
            return '.webp'
        # 从URL获取扩展名
        path = urlparse(url).path
        ext = os.path.splitext(path)[1].lower()
        return ext if ext in ('.jpg', '.jpeg', '.png', '.gif', '.webp') else '.jpg'

    def download_image(self, url: str, character_key: str, index: int) -> bool:
        """
        下载单张图像
        
        Args:
            url: 图像URL
            character_key: 角色标识符
            index: 图像序号
        
        Returns:
            bool: 下载成功返回True
        """
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            data = response.content

            # 验证图像有效性
            if not self._is_valid_image(data):
                print(f"  [跳过] 非有效图像: {url}")
                return False

            # 去重检查
            img_hash = self._compute_hash(data)
            if img_hash in self._downloaded_hashes:
                print(f"  [跳过] 重复图像: {url}")
                return False
            self._downloaded_hashes.add(img_hash)

            # 保存图像
            save_dir = self._get_save_dir(character_key)
            ext = self._get_extension(data, url)
            filename = f"{character_key}_{index:04d}{ext}"
            save_path = save_dir / filename

            with open(save_path, 'wb') as f:
                f.write(data)

            print(f"  [成功] 已保存: {filename} ({len(data) // 1024}KB)")
            return True

        except requests.RequestException as e:
            print(f"  [失败] 下载出错 {url}: {e}")
            return False
        except Exception as e:
            print(f"  [错误] 未知错误 {url}: {e}")
            return False

    def crawl_from_url_list(self, character_key: str, url_list: list, start_index: int = 0) -> int:
        """
        从URL列表批量下载
        
        Args:
            character_key: 角色标识符
            url_list: 图像URL列表
        
        Returns:
            int: 成功下载数量
        """
        char_info = ANIME_CHARACTERS.get(character_key, {})
        char_name = char_info.get("name", character_key)
        anime_name = char_info.get("anime", "未知")
        
        print(f"\n[开始] 下载角色: {char_name}（{anime_name}）")
        print(f"  目标URL数量: {len(url_list)}")
        
        success_count = 0
        for i, url in enumerate(url_list):
            print(f"  [{i+1}/{len(url_list)}] 正在下载...", end="")
            if self.download_image(url, character_key, start_index + i):
                success_count += 1
            time.sleep(self.delay)
        
        print(f"  [完成] 成功下载: {success_count}/{len(url_list)}")
        return success_count

    def check_dataset_status(self) -> dict:
        """
        检查数据集状态
        
        Returns:
            dict: 每个角色的图像数量统计
        """
        status = {}
        for char_key, char_info in ANIME_CHARACTERS.items():
            char_dir = Path(self.output_dir) / char_key
            if char_dir.exists():
                images = list(char_dir.glob("*.jpg")) + \
                         list(char_dir.glob("*.png")) + \
                         list(char_dir.glob("*.webp"))
                count = len(images)
            else:
                count = 0
            
            status[char_key] = {
                "name": char_info["name"],
                "anime": char_info["anime"],
                "count": count,
                "sufficient": count >= MIN_IMAGES_PER_CLASS,
            }
        return status

    def print_status_report(self):
        """打印数据集状态报告"""
        status = self.check_dataset_status()
        
        print("\n" + "="*60)
        print("数据集状态报告")
        print("="*60)
        print(f"{'角色名':<20} {'作品':<15} {'图像数':>8} {'状态':>8}")
        print("-"*60)
        
        total = 0
        sufficient = 0
        for char_key, info in status.items():
            flag = "✓" if info["sufficient"] else "✗"
            print(f"{info['name']:<20} {info['anime']:<15} {info['count']:>8} {flag:>8}")
            total += info["count"]
            if info["sufficient"]:
                sufficient += 1
        
        print("-"*60)
        print(f"总图像数: {total}")
        print(f"达标角色: {sufficient}/{len(status)} (每类≥{MIN_IMAGES_PER_CLASS}张)")
        print("="*60)


# ===== Safebooru 标签映射 =====
# 角色英文 key → Safebooru 搜索标签
SAFEBOORU_TAG_MAP = {
    "naruto_uzumaki": "uzumaki_naruto",
    "sasuke_uchiha": "uchiha_sasuke",
    "sakura_haruno": "haruno_sakura",
    "kakashi_hatake": "hatake_kakashi",
    "monkey_d_luffy": "monkey_d._luffy",
    "roronoa_zoro": "roronoa_zoro",
    "nami": "nami_(one_piece)",
    "sanji": "sanji_(one_piece)",
    "eren_yeager": "eren_yeager",
    "mikasa_ackerman": "mikasa_ackerman",
    "tanjiro_kamado": "tanjiro",
    "nezuko_kamado": "nezuko",
    "izuku_midoriya": "midoriya_izuku",
    "katsuki_bakugo": "bakugou_katsuki",
    "goku": "son_goku",
    "vegeta": "vegeta",
    "ichigo_kurosaki": "kurosaki_ichigo",
    "rukia_kuchiki": "kuchiki_rukia",
    "konata_izumi": "izumi_konata",
    "rem": "rem_(re:zero)",
}


def search_safebooru(tag: str, count: int = 50, max_pages: int = 10) -> list:
    """
    通过 Safebooru API 搜索动漫角色图像 URL。
    
    Safebooru 是免费动漫图库，无需 API Key。
    每个请求最多返回 100 条，通过 pid 分页。
    
    Args:
        tag: Safebooru 标签
        count: 期望获取的 URL 数量
        max_pages: 最大翻页数
    
    Returns:
        list: 图片 URL 列表
    """
    import xml.etree.ElementTree as ET
    
    urls = []
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    }
    
    for pid in range(max_pages):
        if len(urls) >= count:
            break
            
        try:
            params = {
                "page": "dapi",
                "s": "post",
                "q": "index",
                "tags": tag,
                "limit": min(100, count),
                "pid": pid,
            }
            resp = requests.get(
                "https://safebooru.org/index.php",
                params=params,
                headers=headers,
                timeout=20,
            )
            resp.raise_for_status()
            
            root = ET.fromstring(resp.text)
            posts = root.findall("post")
            
            if not posts:
                break  # 没有更多结果
            
            for post in posts:
                file_url = post.get("file_url")
                width = post.get("width", "0")
                height = post.get("height", "0")
                
                if not file_url:
                    continue
                
                # 如果是完整URL直接用，否则拼接
                if not file_url.startswith("http"):
                    directory = post.get("directory", "")
                    if directory:
                        file_url = f"https://safebooru.org/images/{directory}/{file_url}"
                    else:
                        continue
                
                # 过滤掉太小或太大的图
                try:
                    w, h = int(width), int(height)
                    if w < 100 or h < 100 or w > 4000 or h > 4000:
                        continue
                except ValueError:
                    pass
                
                if file_url not in urls:
                    urls.append(file_url)
                    if len(urls) >= count:
                        break
            
            time.sleep(1.0)  # 礼貌性延迟
            
        except Exception as e:
            print(f"  [Safebooru警告] pid={pid}: {e}")
            break
    
    return urls[:count]


def generate_sample_url_list(character_key: str, count: int = 10) -> list:
    """
    生成动漫角色图像 URL 列表。
    优先使用 Safebooru API 获取真实动漫图像。
    """
    char_info = ANIME_CHARACTERS.get(character_key, {})
    char_name = char_info.get("name", character_key)
    anime_name = char_info.get("anime", "")
    
    tag = SAFEBOORU_TAG_MAP.get(character_key, character_key)
    print(f"  [搜索] {char_name}（{anime_name}） tag={tag}")
    
    # 方案1：Safebooru API
    urls = search_safebooru(tag, count)
    
    if urls:
        print(f"  [Safebooru] 获取到 {len(urls)} 个图像 URL")
        return urls
    
    # 方案2：Bing 搜索
    print(f"  [回退] Safebooru 无结果，尝试 Bing...")
    query = f"{char_name} {anime_name} anime character"
    urls = search_bing_images(query, count)
    
    if urls:
        print(f"  [Bing] 获取到 {len(urls)} 个图像 URL")
        return urls
    
    # 方案3：占位图像
    print(f"  [回退] 使用占位图像")
    fallback_urls = []
    char_hash = hashlib.md5(character_key.encode()).hexdigest()[:4]
    for i in range(count):
        seed = int(char_hash, 16) + i
        fallback_urls.append(f"https://picsum.photos/seed/{seed}/224/224")
    return fallback_urls


def search_bing_images(query: str, count: int = 50) -> list:
    """
    Bing 图片搜索（备选方案）。
    """
    urls = []
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    
    offset = 0
    while len(urls) < count and offset < count * 3:
        try:
            params = {
                "q": query,
                "first": offset,
                "count": min(35, count - len(urls) + 10),
            }
            resp = requests.get(
                "https://www.bing.com/images/async",
                params=params,
                headers=headers,
                timeout=15,
            )
            resp.raise_for_status()
            
            murl_matches = re.findall(r'&quot;murl&quot;:&quot;(https?://[^&]+?(?:jpg|jpeg|png|webp)[^&]*?)&quot;', resp.text)
            for url in murl_matches:
                url = url.replace('\\/', '/')
                if url not in urls:
                    urls.append(url)
                    if len(urls) >= count:
                        break
            
            offset += 35
            if len(murl_matches) < 5:
                break
            
        except Exception as e:
            break
    
    return urls[:count]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="动漫角色图像爬取工具（Safebooru + Bing）")
    parser.add_argument("--character", "-c", type=str, default=None,
                        help="指定角色key（默认爬取所有角色）")
    parser.add_argument("--count", "-n", type=int, default=80,
                        help="每个角色下载数量（默认80）")
    parser.add_argument("--delay", "-d", type=float, default=1.0,
                        help="请求间隔秒数（默认1.0）")
    parser.add_argument("--status", "-s", action="store_true",
                        help="仅显示数据集状态")
    parser.add_argument("--subset", action="store_true",
                        help="仅爬取热门角色子集（训练更快）")
    parser.add_argument("--resume", "-r", action="store_true",
                        help="断点续爬：跳过已有足够的角色，继续下载未完成的角色")
    args = parser.parse_args()

    crawler = AnimeImageCrawler(delay=args.delay)

    if args.status:
        crawler.print_status_report()
    else:
        if args.character:
            characters = [args.character]
        elif args.subset:
            # 热门角色子集（Safebooru 标签覆盖率高的）
            characters = [
                "naruto_uzumaki", "sasuke_uchiha", "sakura_haruno",
                "monkey_d_luffy", "roronoa_zoro", "nami",
                "goku", "vegeta",
                "tanjiro_kamado", "nezuko_kamado",
            ]
        else:
            characters = list(ANIME_CHARACTERS.keys())
        
        print(f"\n{'='*60}")
        print(f"  动漫角色图像爬取 - 使用 Safebooru API")
        print(f"  角色数: {len(characters)} | 每角色目标: {args.count} 张")
        print(f"{'='*60}\n")
        
        for char_key in characters:
            if char_key not in ANIME_CHARACTERS:
                print(f"[警告] 未知角色: {char_key}")
                continue

            if args.resume:
                # 实时统计该角色已有图像数
                char_dir = Path(crawler.output_dir) / char_key
                if char_dir.exists():
                    images = list(char_dir.glob("*.jpg")) + \
                             list(char_dir.glob("*.png")) + \
                             list(char_dir.glob("*.webp"))
                    existing = len(images)
                else:
                    existing = 0
                if existing >= args.count:
                    char_info = ANIME_CHARACTERS.get(char_key, {})
                    print(f"\n[跳过] {char_info.get('name', char_key)} 已有 {existing} 张，达标")
                    continue
                needed = args.count - existing
                next_idx = crawler._get_next_index(char_key)
                char_info = ANIME_CHARACTERS.get(char_key, {})
                print(f"\n[续爬] {char_info.get('name', char_key)} 已有 {existing} 张，需再下载 {needed} 张")
                url_list = generate_sample_url_list(char_key, needed)
                crawler.crawl_from_url_list(char_key, url_list, start_index=next_idx)
            else:
                url_list = generate_sample_url_list(char_key, args.count)
                crawler.crawl_from_url_list(char_key, url_list)
        
        crawler.print_status_report()
