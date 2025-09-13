from bs4 import BeautifulSoup
import os
import re
import requests
import urllib.parse
import time
from datetime import datetime
from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

try:
    from googleapiclient.discovery import build
    GOOGLE_API_AVAILABLE = True
except ImportError:
    GOOGLE_API_AVAILABLE = False
    # Google API client không có sẵn

@CrewBase
class Chatbot1thegioiCrew():
    """Chatbot tìm kiếm dựa trên input người dùng qua Google site search"""

    agents_config = 'config/agents.yaml'
    tasks_config = 'config/tasks.yaml'

    def __init__(self):
        # Google Custom Search API configuration
        self.google_api_key = os.getenv('GOOGLE_API_KEY')  # Từ environment variable
        self.google_cx = os.getenv('GOOGLE_CX')  # Custom Search Engine ID
        
        if not self.google_api_key or not self.google_cx:
            # Google API Key hoặc CX không được cấu hình
            self.use_google_api = False
        else:
            self.use_google_api = GOOGLE_API_AVAILABLE
            # Google Custom Search API đã sẵn sàng

    def search_topic_articles(self, topic):
        """Tìm kiếm bài viết dựa trên input của người dùng qua Google site search"""
        return self.search_via_google_site(topic)

    def search_via_google_api(self, topic):
        """Tìm kiếm bằng Google Custom Search API với site: search"""
        articles = []
        
        if not self.use_google_api:
            # Google API không khả dụng
            return []
        
        try:
            # Tìm kiếm Google Custom Search API
            
            # Tạo service object
            service = build("customsearch", "v1", developerKey=self.google_api_key)
            
            # Các query tìm kiếm khác nhau
            search_queries = [
                f"{topic} site:1thegioi.vn",
                f'"{topic}" site:1thegioi.vn',
                f"{topic} tin tức site:1thegioi.vn",
                f"{topic} mới nhất site:1thegioi.vn"
            ]
            
            seen_urls = set()
            
            for i, query in enumerate(search_queries, 1):
                if len(articles) >= 8:  # Giới hạn 8 bài từ API
                    break
                
                try:
                    # API Query
                    
                    # Gọi Google Custom Search API
                    result = service.cse().list(
                        q=query,
                        cx=self.google_cx,
                        num=10,  # Số kết quả mỗi query
                        lr='lang_vi',  # Ưu tiên tiếng Việt
                        safe='off',
                        sort='date'  # Sắp xếp theo ngày
                    ).execute()
                    
                    items = result.get('items', [])
                    # Xử lý kết quả API
                    
                    for item in items:
                        if len(articles) >= 8:
                            break
                            
                        url = item.get('link', '')
                        title = item.get('title', '')
                        snippet = item.get('snippet', '')
                        
                        # Kiểm tra điều kiện
                        if (url and title and 
                            '1thegioi.vn' in url and 
                            url.endswith('.html') and
                            url not in seen_urls and
                            len(title) > 15 and
                            not any(skip in url.lower() for skip in ['tag', 'author', 'search', 'category'])):
                            
                            # Tính điểm liên quan
                            keywords = self.extract_keywords(topic)
                            relevance_score = self.calculate_relevance_score(title, url, topic, keywords)
                            
                            if relevance_score > 2.0:  # Ngưỡng cho API results
                                # Lấy nội dung đầy đủ
                                content = self.get_article_content(url)
                                
                                # Tính điểm nội dung
                                content_score = self.calculate_content_relevance(content, topic, keywords)
                                total_score = relevance_score + content_score * 0.4
                                
                                if total_score > 2.5:
                                    articles.append({
                                        'title': title.strip(),
                                        'url': url,
                                        'content': content,
                                        'snippet': snippet,
                                        'relevance_score': total_score,
                                        'source': f'google_api_query_{i}'
                                    })
                                    
                                    seen_urls.add(url)
                                    # Thêm bài viết từ API
                    
                    # Nghỉ giữa các query để tránh rate limit
                    time.sleep(0.5)
                    
                except Exception as e:
                    # Lỗi API query
                    continue
            
            # Sắp xếp theo điểm liên quan
            articles = sorted(articles, key=lambda x: x.get('relevance_score', 0), reverse=True)
            
            if articles:
                # Có kết quả từ API
                pass
            
            return articles
            
        except Exception as e:
            # Lỗi Google Custom Search API
            return []

    def search_via_google_site(self, topic):
        """Tìm kiếm bài viết chỉ trên 1thegioi.vn và tạo báo cáo tóm tắt"""
        
        articles = []
        try:
            # Bước 1: Tìm kiếm trực tiếp trên 1thegioi.vn
            direct_articles = self.search_direct_1thegioi(topic)
            if direct_articles:
                articles.extend(direct_articles)
            
            # Bước 2: Nếu chưa đủ 3 bài, dùng Google Custom Search API (chỉ tìm trên 1thegioi.vn)
            if len(articles) < 3 and self.use_google_api:
                api_articles = self.search_via_google_api(topic)
                if api_articles:
                    # Lọc loại bỏ duplicate
                    new_articles = []
                    for article in api_articles:
                        if not any(existing['url'] == article['url'] for existing in articles):
                            new_articles.append(article)
                    articles.extend(new_articles)
                    # Thêm bài viết từ Google API
                else:
                    # Google API không trả về kết quả
                    pass

            # Bước 3: Nếu vẫn chưa đủ 3 bài, dùng Google web scraping (chỉ tìm trên 1thegioi.vn)
            if len(articles) < 3:
                google_articles = self.search_via_google_site_core(topic)
                if google_articles:
                    new_articles = []
                    for article in google_articles:
                        if not any(existing['url'] == article['url'] for existing in articles):
                            new_articles.append(article)
                    articles.extend(new_articles)
                    # Thêm bài viết từ Google scraping
                else:
                    # Google scraping không trả về kết quả
                    pass

            # Bước 4: Cuối cùng, thử sitemap search trên 1thegioi.vn
            if len(articles) < 3:
                sitemap_articles = self.search_via_sitemap(topic)
                if sitemap_articles:
                    new_articles = []
                    for article in sitemap_articles:
                        if not any(existing.get('url', '') == article.get('url', '') for existing in articles):
                            new_articles.append(article)
                    articles.extend(new_articles)
                    # Thêm bài viết từ sitemap
                else:
                    # Sitemap không trả về kết quả
                    pass

            # Xử lý kết quả
            if articles:
                # Sắp xếp theo relevance score
                articles_with_score = [a for a in articles if 'relevance_score' in a]
                articles_without_score = [a for a in articles if 'relevance_score' not in a]

                if articles_with_score:
                    articles_with_score.sort(key=lambda x: x['relevance_score'], reverse=True)
                    articles = articles_with_score + articles_without_score

                # Lấy đúng 3 bài liên quan nhất
                final_articles = articles[:3]

                # Hoàn tất tìm kiếm và tạo báo cáo

                # Tạo báo cáo tóm tắt
                return self.create_manual_report(topic, final_articles)
            else:
                # Không tìm thấy bài viết - tạo báo cáo tổng quan
                return self.create_default_report(topic)
                
        except Exception as e:
            # Lỗi trong quá trình tìm kiếm
            return self.create_default_report(topic)

    def search_via_google_site_core(self, topic):
        """Core Google site search functionality - tìm kiếm chính xác theo input người dùng"""
        articles = []
        try:
            # Tạo các query tìm kiếm chính xác theo topic
            search_queries = [
                f"site:1thegioi.vn \"{topic}\"",  # Exact phrase trước
                f"site:1thegioi.vn {topic}",     # General search
                f"site:1thegioi.vn {topic} 2024 2025",  # Recent articles
                f"site:1thegioi.vn \"{topic}\" tin tức mới nhất"  # Latest news
            ]
            
            seen_urls = set()
            
            for i, query in enumerate(search_queries, 1):
                if len(articles) >= 5:  # Giới hạn 5 bài
                    break
                    
                # Tìm kiếm với query
                
                encoded_query = urllib.parse.quote_plus(query)
                google_url = f"https://www.google.com/search?q={encoded_query}&num=10"
                
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'vi-VN,vi;q=0.8,en-US;q=0.5,en;q=0.3',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Cache-Control': 'max-age=0'
                }
                
                try:
                    # Truy cập Google search
                    response = requests.get(google_url, headers=headers, timeout=20)
                    
                    if response.status_code == 200:
                        soup = BeautifulSoup(response.content, 'html.parser')
                        
                        # Kiểm tra xem có bị chặn không
                        if "Our systems have detected unusual traffic" in response.text:
                            # Google đã chặn request
                            continue
                        
                        # Thử nhiều selectors để tìm kết quả Google (cập nhật 2024-2025)
                        selectors = [
                            # Main result containers
                            'div[data-ved]', 'div[data-hveid]', 'div[data-ctid]',
                            'div.g', 'div.tF2Cxc', 'div.MjjYud', 'div.yuRUbf',
                            'div.kCrYT', 'div.egMi0', 'div.Gx5Zad', 'div.IsZvec',

                            # Link containers
                            'div[data-ved] a', 'div.tF2Cxc a', 'div.MjjYud a',
                            'div.yuRUbf a', 'div.kCrYT a', 'div.egMi0 a',

                            # Title selectors
                            'h3', '.LC20lb', 'a h3', 'a .LC20lb',
                            'div[data-ved] h3', 'div.tF2Cxc h3', 'div.MjjYud h3',

                            # Alternative containers (2024-2025 patterns)
                            'div[data-snf]', 'div[data-ved] div', 'div.tF2Cxc div',
                            'div.MjjYud div', 'div.yuRUbf div', 'div.kCrYT div',

                            # Mobile/desktop variations
                            '.srg .g', '.srg div[data-ved]', '.srg .tF2Cxc',
                            '.srg .MjjYud', '.srg .yuRUbf', '.srg .kCrYT'
                        ]
                        search_results = []
                        
                        for selector in selectors:
                            search_results = soup.select(selector)
                            if search_results:
                                # Tìm thấy kết quả với selector
                                break
                        
                        if not search_results:
                            # Không tìm thấy kết quả với selector - thử tìm links 1thegioi.vn
                            all_links = soup.find_all('a', href=True)
                            
                            for link in all_links[:20]:  # Kiểm tra 20 links đầu
                                href = link.get('href', '')
                                if '1thegioi.vn' in href:
                                    # Tìm thấy link 1thegioi.vn
                                    break
                        
                        results_found = 0
                        for result in search_results[:20]:  # Tăng lên 20 kết quả
                            if len(articles) >= 5:
                                break

                            try:
                                # Tìm link với nhiều cách khác nhau
                                link_elem = None
                                url = ""
                                title = ""

                                # Cách 1: Nếu result là link trực tiếp
                                if result.name == 'a':
                                    link_elem = result
                                    url = link_elem.get('href', '')
                                    title = link_elem.get_text(strip=True)
                                else:
                                    # Cách 2: Tìm link trong container
                                    link_elem = result.find('a', href=True)
                                    if link_elem:
                                        url = link_elem.get('href', '')
                                        title = link_elem.get_text(strip=True)

                                # Cách 3: Tìm title riêng biệt nếu chưa có
                                if not title or len(title) < 5:
                                    title_elem = result.find('h3')
                                    if title_elem:
                                        title = title_elem.get_text(strip=True)
                                    else:
                                        # Thử các selector khác cho title
                                        for title_sel in ['h3', '.LC20lb', 'a h3', 'a .LC20lb']:
                                            title_elem = result.select_one(title_sel)
                                            if title_elem:
                                                title = title_elem.get_text(strip=True)
                                                break

                                # Xử lý URL Google redirect
                                if url.startswith('/url?q='):
                                    url = urllib.parse.unquote(url.split('/url?q=')[1].split('&')[0])
                                elif url.startswith('http://www.google.com/url?q='):
                                    url = urllib.parse.unquote(url.split('http://www.google.com/url?q=')[1].split('&')[0])

                                # Kiểm tra URL hợp lệ
                                if not url or not url.startswith('http') or '1thegioi.vn' not in url:
                                    continue

                                if url in seen_urls:
                                    continue

                                # Lọc các URL không mong muốn
                                if any(skip in url.lower() for skip in ['tag', 'author', 'search', 'category', 'page', 'comment', 'event']):
                                    continue

                                # Kiểm tra title hợp lệ
                                if len(title) < 10:
                                    continue

                                # Tính điểm liên quan
                                keywords = self.extract_keywords(topic)
                                relevance_score = self.calculate_relevance_score(title, url, topic, keywords)

                                if relevance_score > 1.0:  # Ngưỡng cho Google results
                                    # Lấy nội dung bài viết
                                    content = self.get_article_content(url)

                                    if content and len(content) > 100:  # Đảm bảo có nội dung
                                        articles.append({
                                            'title': title.strip(),
                                            'url': url,
                                            'content': content,
                                            'relevance_score': relevance_score,
                                            'source': f'google_query_{i}'
                                        })

                                        seen_urls.add(url)
                                        results_found += 1
                                        # Thêm bài viết từ Google

                            except Exception as e:
                                # Lỗi xử lý kết quả Google
                                continue

                        # Hoàn thành query
                                
                    else:
                        # HTTP Error
                        if response.status_code == 429:
                            # Rate limited by Google
                            time.sleep(2)
                        
                except Exception as e:
                    # Lỗi query
                    continue
                    
            return articles
            
        except Exception as e:
            # Lỗi Google search
            return []

    def search_direct_1thegioi(self, topic):
        """Tìm kiếm trực tiếp trên 1thegioi.vn - phương pháp chính để tìm bài viết liên quan"""
        articles = []
        try:
            # Tìm kiếm trên 1thegioi.vn
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'vi-VN,vi;q=0.8,en-US;q=0.5,en;q=0.3',
                'Accept-Encoding': '',  # Không yêu cầu compression để tránh lỗi parsing
                'Connection': 'keep-alive'
            }
            
            # Lấy các trang có thể chứa bài viết liên quan
            search_pages = self.get_relevant_pages(topic)
            topic_keywords = self.extract_keywords(topic)
            seen_urls = set()
            
            # Trích xuất từ khóa tìm kiếm
            
            for page_url in search_pages:
                if len(articles) >= 8:  # Tăng lên 8 bài để có nhiều lựa chọn hơn
                    break
                    
                try:
                    # Quét trang web
                    response = requests.get(page_url, headers=headers, timeout=15)
                    
                    if response.status_code == 200:
                        # Xử lý encoding tốt hơn
                        response.encoding = response.apparent_encoding or 'utf-8'
                        
                        # Sử dụng text thay vì content để tránh lỗi encoding
                        soup = BeautifulSoup(response.text, 'html.parser')
                        
                        # Tìm các bài viết trên trang với selectors được cập nhật và tối ưu
                        article_links = []

                        # Các selectors ưu tiên cho 1thegioi.vn (dựa trên cấu trúc thực tế)
                        article_selectors = [
                            # 1thegioi.vn specific selectors
                            'a[href*=".html"]',  # Lấy tất cả links có .html
                        ]

                        # Tìm articles theo từng selector
                        found_urls = set()
                        for selector in article_selectors:
                            if len(article_links) >= 50:  # Tăng giới hạn
                                break

                            links = soup.select(selector)
                            # Tìm articles theo selector
                            
                            for link in links:
                                if len(article_links) >= 50:
                                    break

                                href = link.get('href', '')
                                if href and href not in found_urls:
                                    # Đảm bảo URL đầy đủ
                                    if href.startswith('/'):
                                        href = f'https://1thegioi.vn{href}'
                                    elif not href.startswith('http'):
                                        href = f'https://1thegioi.vn/{href}'
                                    
                                    if '1thegioi.vn' in href and href.endswith('.html'):
                                        article_links.append(link)
                                        found_urls.add(href)
                        
                        # Thu thập bài viết từ trang
                        
                        # Xử lý từng bài viết
                        page_articles_found = 0
                        for link in article_links:
                            if len(articles) >= 8:
                                break
                                
                            try:
                                href = link.get('href', '')
                                if href.startswith('/'):
                                    href = f'https://1thegioi.vn{href}'
                                elif not href.startswith('http'):
                                    href = f'https://1thegioi.vn/{href}'
                                    
                                if href in seen_urls or not href.endswith('.html'):
                                    continue
                                
                                # Lấy title từ link
                                title = link.get('title', '') or link.get_text().strip()
                                
                                # Làm sạch title
                                if not title or len(title) < 10:
                                    continue
                                    
                                title = title.replace('\n', ' ').replace('\t', ' ')
                                title = ' '.join(title.split())  # Loại bỏ space thừa
                                
                                if len(title) > 200:  # Cắt title quá dài
                                    title = title[:200] + '...'
                                
                                # Tính điểm liên quan
                                relevance_score = self.calculate_relevance_score(title, href, topic, topic_keywords)
                                
                                # Kiểm tra và lọc bài viết chất lượng
                                min_score = 0.8 if len(title) > 30 else 1.0
                                
                                if relevance_score >= min_score:
                                    # Lấy nội dung bài viết
                                    content = self.get_article_content(href)
                                    
                                    if content and len(content) > 200:  # Đảm bảo có nội dung đủ
                                        # Tính điểm nội dung để double-check
                                        content_score = self.calculate_content_relevance(content, topic, topic_keywords)
                                        final_score = (relevance_score + content_score) / 2
                                        
                                        if final_score >= 0.5:  # Ngưỡng cuối cùng thấp hơn để không bỏ lỡ bài viết liên quan
                                            articles.append({
                                                'title': title,
                                                'url': href,
                                                'content': content,
                                                'relevance_score': final_score,
                                                'source': 'direct_1thegioi'
                                            })
                                            
                                            seen_urls.add(href)
                                            page_articles_found += 1
                                            # Bài viết chất lượng được chọn
                                        else:
                                            # Điểm nội dung không đủ cao
                                            pass
                                    else:
                                        # Không thể lấy nội dung
                                        pass
                                else:
                                    # Điểm liên quan không đủ cao
                                    pass
                                    
                            except Exception as e:
                                # Lỗi xử lý link
                                continue
                        
                        # Hoàn thành quét trang
                        
                    else:
                        # Lỗi HTTP
                        pass
                        
                    # Nghỉ giữa các trang để tránh overload
                    time.sleep(1)
                        
                except Exception as e:
                    # Lỗi xử lý trang
                    continue
            
            if articles:
                # Sắp xếp theo điểm liên quan
                articles = sorted(articles, key=lambda x: x.get('relevance_score', 0), reverse=True)
                # Tìm kiếm hoàn thành
            else:
                # Không tìm thấy bài viết phù hợp
                pass
            
            return articles[:3]  # Chỉ trả về 3 bài chất lượng cao nhất
            
        except Exception as e:
            # Lỗi tìm kiếm trực tiếp
            return []

    def get_relevant_pages(self, topic):
        """Lấy danh sách các chuyên mục chính và trang chủ để tìm kiếm trên toàn bộ 1thegioi.vn cho mọi chủ đề"""
        topic_lower = topic.lower()
        
        # Danh sách chuyên mục chính (có thể mở rộng nếu cần)
        main_sections = [
            '',  # Trang chủ
            'thoi-su',
            'kinh-te-40',
            'ai-blockchain',
            'nhip-dap-cong-nghe',
            'dot-pha',
            'ca-phe-mot-the-gioi',
            'cong-nghe-quan-su',  # Military technology section
            'the-thao',
            'giai-tri',
            'suc-khoe',
            'doi-song',
            'quoc-te',
            'giao-duc',
            'moi-truong',
            'phap-luat',
            'van-hoa',
            'du-lich',
            'ban-doc',
            'video',
        ]
        
        # Ưu tiên các trang liên quan đến chủ đề
        if any(term in topic_lower for term in ['quân sự', 'military', 'quân đội', 'vũ khí', 'chiến tranh', 'quốc phòng']):
            # Đưa trang công nghệ quân sự lên đầu
            prioritized_sections = ['cong-nghe-quan-su', 'thoi-su', 'quoc-te', 'ca-phe-mot-the-gioi'] + main_sections
            main_sections = list(dict.fromkeys(prioritized_sections))  # Loại bỏ duplicate
        
        elif any(term in topic_lower for term in ['y tế', 'sức khỏe', 'health', 'medical', 'bệnh viện', 'bác sĩ']):
            # Đưa trang sức khỏe và thời sự lên đầu
            prioritized_sections = ['suc-khoe', 'thoi-su', 'nhip-dap-cong-nghe', 'doi-song'] + main_sections
            main_sections = list(dict.fromkeys(prioritized_sections))  # Loại bỏ duplicate
        
        # Tạo URL đầy đủ cho từng chuyên mục
        full_urls = [f'https://1thegioi.vn/{section}' if section else 'https://1thegioi.vn/' for section in main_sections]
        # Loại bỏ trùng lặp
        unique_urls = list(dict.fromkeys(full_urls))
        # Giới hạn số lượng trang nếu cần (ở đây lấy tối đa 12 trang đầu tiên cho chủ đề quân sự)
        limit = 12 if any(term in topic_lower for term in ['quân sự', 'military']) else 10
        return unique_urls[:limit]

    def extract_keywords(self, topic):
        """Trích xuất từ khóa chính từ topic"""
        import re
        
        # Làm sạch và tách từ
        clean_topic = re.sub(r'[^\w\s]', ' ', topic.lower())
        words = [word.strip() for word in clean_topic.split() if len(word) > 2]
        
        # Thêm từ khóa liên quan
        related = self.get_related_keywords(topic)
        
        return words + related

    def calculate_relevance_score(self, title, url, topic, keywords):
        """Tính điểm liên quan CHÍNH XÁC - Tập trung vào liên quan trực tiếp"""
        score = 0.0
        
        title_lower = title.lower().strip()
        topic_lower = topic.lower().strip()
        url_lower = url.lower()
        
        # 1. EXACT TOPIC MATCH - Điểm rất cao cho khớp chính xác
        if topic_lower in title_lower:
            score += 25.0  # Tăng điểm cao cho exact match
        
        # 2. Kiểm tra từng từ quan trọng của topic - Tăng điểm
        topic_words = [word for word in topic_lower.split() if len(word) > 2]
        critical_matches = 0
        
        for word in topic_words:
            if word in title_lower:
                score += 8.0  # Tăng điểm từ 4.0 lên 8.0
                critical_matches += 1
        
        # 3. STRICT FILTERING - Loại bỏ bài không liên quan trực tiếp
        forbidden_terms = []
        required_terms = []
        
        # Định nghĩa CHẶT CHẼ hơn cho từng topic
        if any(term in topic_lower for term in ['y tế', 'sức khỏe', 'health', 'medical', 'bệnh viện', 'bác sĩ']):
            required_terms = ['y tế', 'sức khỏe', 'health', 'medical', 'bệnh viện', 'bác sĩ', 'doctor', 'điều trị', 'bệnh nhân', 'phòng khám', 'thuốc', 'vaccine', 'cấp cứu', 'phẫu thuật', 'sinh', 'thai', 'nhi', 'khoa', 'viện', 'cdc', 'y khoa', 'nhập viện', 'hồi sức', 'icu']
            forbidden_terms = ['công nghệ', 'ai', 'blockchain', 'thể thao', 'giải trí', 'chính trị', 'kinh tế']
            
        elif any(term in topic_lower for term in ['công nghệ', 'technology', 'ai', 'tech', 'blockchain']):
            required_terms = ['công nghệ', 'technology', 'tech', 'ai', 'artificial intelligence', 'blockchain', 'crypto', 'digital', 'innovation', 'internet', 'software', 'app', 'smartphone']
            forbidden_terms = ['y tế', 'bệnh viện', 'thể thao', 'giải trí', 'chiến tranh', 'quân sự']
            
        elif any(term in topic_lower for term in ['chiến tranh', 'quân sự', 'war', 'military', 'vũ khí']):
            required_terms = ['chiến tranh', 'war', 'ukraine', 'russia', 'quân sự', 'military', 'vũ khí', 'weapon', 'nato', 'army', 'quân đội', 'quốc phòng', 'patriot', 'tên lửa', 'missile', 'tank', 'fighter', 'aircraft', 'navy', 'airforce', 'drone', 'radar', 'defense', 'tàu chiến', 'máy bay', 'hạm đội', 'binh sĩ', 'tác chiến', 'chiến đấu', 'phòng không', 'tấn công', 'pháo', 'súng', 'b-52', 'f-16', 'himars', 'triều tiên', 'hàn quốc', 'israel', 'palestine', 'gaza']
            forbidden_terms = ['y tế', 'công nghệ', 'ai', 'thể thao', 'giải trí', 'kinh tế']
            
        elif any(term in topic_lower for term in ['kinh tế', 'economy', 'tài chính', 'finance']):
            required_terms = ['kinh tế', 'economy', 'tài chính', 'finance', 'chứng khoán', 'stock', 'market', 'investment', 'banking', 'trade', 'doanh nghiệp', 'company']
            forbidden_terms = ['y tế', 'thể thao', 'giải trí', 'thiên tai', 'chiến tranh']
            
        elif any(term in topic_lower for term in ['thể thao', 'sports', 'bóng đá', 'football']):
            required_terms = ['thể thao', 'sports', 'bóng đá', 'football', 'soccer', 'world cup', 'olympic', 'vô địch', 'champion', 'thi đấu', 'giải đấu']
            forbidden_terms = ['y tế', 'công nghệ', 'ai', 'chính trị', 'kinh tế']
            
        elif any(term in topic_lower for term in ['môi trường', 'environment', 'sinh thái', 'khí hậu', 'climate']):
            required_terms = ['môi trường', 'environment', 'sinh thái', 'ecology', 'bảo tồn', 'conservation', 'ô nhiễm', 'pollution', 'khí hậu', 'climate', 'carbon', 'xanh', 'green', 'bền vững', 'sustainable', 'rác thải', 'waste', 'tái chế', 'recycle', 'năng lượng tái tạo', 'renewable', 'biodiversity', 'đa dạng sinh học']
            forbidden_terms = ['quân sự', 'chiến tranh', 'thể thao', 'giải trí', 'chính trị']
            
        elif any(term in topic_lower for term in ['giáo dục', 'education', 'trường học', 'school', 'đại học']):
            required_terms = ['giáo dục', 'education', 'trường học', 'school', 'đại học', 'university', 'học sinh', 'student', 'giáo viên', 'teacher', 'học tập', 'learning', 'đào tạo', 'training', 'khóa học', 'course']
            forbidden_terms = ['quân sự', 'chiến tranh', 'thể thao', 'giải trí']
            
        else:
            # Topic tổng quát - Áp dụng từ khóa chính của topic
            required_terms = topic_words + self.get_related_keywords(topic)[:5]  # Giảm từ 10 xuống 5
            forbidden_terms = []
        
        # Kiểm tra từ cấm - LOẠI BỎ NGHIÊM NGẶT
        if forbidden_terms:
            for term in forbidden_terms:
                if term in title_lower:
                    return 0.0  # Loại bỏ hoàn toàn bài viết không liên quan
        
        # Kiểm tra có từ liên quan không - CHẶT CHẼ HỚN
        has_required = False
        exact_required_matches = 0
        
        for term in required_terms:
            if term in title_lower:
                has_required = True
                score += 5.0  # Tăng bonus từ 2.0 lên 5.0
                exact_required_matches += 1
        
        # NGƯỠNG CÂN BẰNG - Chặt chẽ nhưng hợp lý cho từng chủ đề
        topic_lower = str(topic).lower()
        if any(word in topic_lower for word in ['chiến tranh', 'quân sự', 'war', 'military', 'ukraine', 'russia']):
            min_threshold = 6.0  # Giảm từ 8.0 xuống 6.0 cho quân sự vì ít bài hơn
        elif any(word in topic_lower for word in ['y tế', 'health', 'medical', 'bệnh viện']):
            min_threshold = 12.0  # Y tế có nhiều bài, ngưỡng cao hơn
        elif any(word in topic_lower for word in ['công nghệ', 'technology', 'ai', 'tech']):
            min_threshold = 12.0  # Công nghệ có nhiều bài, ngưỡng cao hơn
        elif any(word in topic_lower for word in ['kinh tế', 'economy', 'economic']):
            min_threshold = 12.0  # Kinh tế có nhiều bài, ngưỡng cao hơn
        else:
            min_threshold = 10.0  # Ngưỡng mặc định
        
        # Nếu không có từ bắt buộc -> loại bỏ
        if not has_required:
            return 0.0
        
        # Nếu điểm thấp hơn ngưỡng -> loại bỏ
        if score < min_threshold:
            return 0.0
        
        # 4. URL bonus cho các từ khóa chính
        for word in topic_words:
            if word in url_lower:
                score += 3.0  # Tăng từ 1.0 lên 3.0
        
        # 5. Bonus cho số lượng từ khóa match nhiều
        if critical_matches >= len(topic_words):  # Tất cả từ khóa phải match
            score += 10.0  # Tăng từ 3.0 lên 10.0
        elif critical_matches >= len(topic_words) * 0.8:  # 80% từ khóa match
            score += 5.0
        
        return max(0, score)

    def get_irrelevant_terms(self, topic):
        """Lấy danh sách từ khóa không liên quan đến topic cụ thể"""
        irrelevant_terms = []
        
        # Nếu tìm về thiên tai -> loại bỏ tech terms
        if any(word in topic for word in ['thiên tai', 'động đất', 'lũ lụt', 'bão', 'tsunami']):
            irrelevant_terms.extend(['ai', 'chatgpt', 'technology', 'tech', 'blockchain', 'crypto', 'robot'])
        
        # Nếu tìm về công nghệ -> loại bỏ disaster terms  
        elif any(word in topic for word in ['công nghệ', 'ai', 'tech', 'blockchain']):
            irrelevant_terms.extend(['thiên tai', 'động đất', 'lũ lụt', 'bão', 'thể thao', 'giải trí'])
        
        # Nếu tìm về chính trị -> loại bỏ tech/disaster terms
        elif any(word in topic for word in ['chính trị', 'bầu cử', 'tổng thống', 'ngoại giao']):
            irrelevant_terms.extend(['ai', 'chatgpt', 'technology', 'thiên tai', 'thể thao'])
        
        # Nếu tìm về thể thao -> loại bỏ politics/tech terms
        elif any(word in topic for word in ['thể thao', 'bóng đá', 'world cup', 'olympic']):
            irrelevant_terms.extend(['chính trị', 'ai', 'technology', 'thiên tai', 'kinh tế'])
        
        # Nếu tìm về kinh tế -> loại bỏ sports/disaster terms
        elif any(word in topic for word in ['kinh tế', 'tài chính', 'chứng khoán', 'ngân hàng']):
            irrelevant_terms.extend(['thể thao', 'bóng đá', 'thiên tai', 'giải trí'])
        
        # Các từ thường không liên quan chung
        general_irrelevant = ['quảng cáo', 'ads', 'advertisement', 'sponsored', 'promotion']
        irrelevant_terms.extend(general_irrelevant)
        
        return irrelevant_terms

    def calculate_content_relevance(self, content, topic, keywords):
        """Tính điểm liên quan dựa trên nội dung"""
        if not content or len(content) < 50:
            return 0
        
        score = 0
        content_lower = content.lower()
        topic_lower = topic.lower()
        
        # Topic chính xác trong content
        if topic_lower in content_lower:
            score += 2.0
        
        # Keywords trong content
        for keyword in keywords:
            if len(keyword) > 2 and keyword in content_lower:
                score += 0.3
        
        return min(score, 3.0)  # Giới hạn tối đa 3 điểm

    def xml_to_dict(self, element):
        """Convert XML element to dictionary for easier processing"""
        result = {}
        if hasattr(element, 'tag'):
            result[element.tag] = {}

            # Add attributes
            if hasattr(element, 'attrib'):
                for key, value in element.attrib.items():
                    result[element.tag][f"@{key}"] = value

            # Add text content
            if hasattr(element, 'text') and element.text and element.text.strip():
                result[element.tag]["#text"] = element.text.strip()

            # Process children
            for child in element:
                child_dict = self.xml_to_dict(child)
                for key, value in child_dict.items():
                    if key in result[element.tag]:
                        if not isinstance(result[element.tag][key], list):
                            result[element.tag][key] = [result[element.tag][key]]
                        result[element.tag][key].append(value)
                    else:
                        result[element.tag][key] = value

        return result

    def extract_urls_from_dict(self, data):
        """Extract URLs from dictionary format XML"""
        urls = []

        def traverse_dict(d, path=""):
            if isinstance(d, dict):
                for key, value in d.items():
                    if key in ['url', 'item', 'entry']:
                        if isinstance(value, dict):
                            # Try to find loc or link
                            loc = value.get('loc', {}).get('#text') or value.get('link', {}).get('#text')
                            if loc:
                                urls.append((loc, value))
                    elif isinstance(value, (dict, list)):
                        traverse_dict(value, f"{path}.{key}")
            elif isinstance(d, list):
                for item in d:
                    traverse_dict(item, path)

        traverse_dict(data)
        return urls

    def get_related_keywords(self, topic):
        """Tạo từ khóa liên quan chính xác cho topic cụ thể - Ưu tiên tiếng Việt"""
        topic_lower = topic.lower().strip()
        related = []
        
        # Từ điển từ khóa liên quan CHÍNH XÁC - mỗi chủ đề chỉ có từ khóa liên quan trực tiếp
        keyword_relations = {
            # Y TẾ - Mở rộng từ khóa
            'y tế': ['y tế', 'sức khỏe', 'y học', 'điều trị', 'bệnh viện', 'bác sĩ', 'y khoa', 'chăm sóc sức khỏe', 'phòng khám', 'bệnh nhân', 'thuốc', 'y tế công cộng', 'bảo hiểm y tế', 'hệ thống y tế', 'khám bệnh', 'chữa bệnh', 'cấp cứu', 'phẫu thuật', 'sinh', 'đẻ', 'thai sản', 'nhi khoa', 'tim mạch', 'ung thư', 'cancer', 'vaccine', 'tiêm chủng', 'hồi sức', 'icu', 'bệnh', 'tử vong', 'ca bệnh', 'nhiễm trùng', 'vi khuẩn', 'virus', 'dịch bệnh', 'kháng sinh', 'antibiotic', 'tế bào', 'gene', 'dna', 'xét nghiệm', 'chẩn đoán', 'triệu chứng', 'hội chứng', 'syndrome'],
            'sức khỏe': ['sức khỏe', 'y tế', 'khỏe mạnh', 'chăm sóc sức khỏe', 'tập luyện', 'dinh dưỡng', 'bệnh', 'điều trị', 'phòng bệnh'],
            'bệnh viện': ['bệnh viện', 'y tế', 'bác sĩ', 'điều trị', 'phòng khám', 'khoa', 'viện', 'trung tâm y tế', 'phẫu thuật', 'cấp cứu', 'nhập viện', 'xuất viện'],
            'bác sĩ': ['bác sĩ', 'doctor', 'y tế', 'điều trị', 'khám bệnh', 'chữa bệnh', 'bệnh viện', 'phòng khám', 'y khoa', 'chuyên khoa'],
            'covid': ['covid', 'coronavirus', 'đại dịch', 'sars-cov-2', 'y tế', 'vaccine', 'f0', 'f1', 'cách ly', 'phong tỏa'],
            'vaccine': ['vaccine', 'tiêm chủng', 'miễn dịch', 'y tế', 'phòng bệnh', 'vắc xin'],
            
            # CÔNG NGHỆ - Mở rộng
            'công nghệ': ['công nghệ', 'technology', 'tech', 'kỹ thuật', 'số hóa', 'đổi mới', 'innovation', 'digital', 'IT', 'phần mềm', 'ứng dụng', 'internet'],
            'ai': ['AI', 'artificial intelligence', 'trí tuệ nhân tạo', 'học máy', 'machine learning', 'deep learning', 'neural network', 'chatgpt', 'công nghệ'],
            'blockchain': ['blockchain', 'tiền mã hóa', 'cryptocurrency', 'bitcoin', 'crypto', 'công nghệ'],
            'technology': ['technology', 'công nghệ', 'tech', 'innovation', 'digital'],
            
            # KINH TẾ - Mở rộng
            'kinh tế': ['kinh tế', 'economy', 'tăng trưởng', 'suy thoái', 'lạm phát', 'GDP', 'thị trường', 'tài chính', 'doanh nghiệp', 'đầu tư'],
            'tài chính': ['tài chính', 'finance', 'ngân hàng', 'đầu tư', 'investment', 'tiền tệ', 'kinh tế'],
            'chứng khoán': ['chứng khoán', 'stock market', 'thị trường', 'cổ phiếu', 'giao dịch', 'tài chính'],
            
            # QUÂN SỰ - Mở rộng
            'quân sự': ['quân sự', 'military', 'quân đội', 'quốc phòng', 'defense', 'vũ khí', 'weapon', 'chiến tranh', 'war', 'an ninh', 'security', 'bộ quốc phòng', 'army', 'navy', 'air force'],
            'chiến tranh': ['chiến tranh', 'war', 'conflict', 'xung đột', 'quân sự', 'military', 'ukraine', 'russia', 'nato', 'quân đội', 'weapon', 'vũ khí'],
            'quân đội': ['quân đội', 'army', 'military', 'quân sự', 'lính', 'soldier', 'chiến sĩ', 'defense'],
            'vũ khí': ['vũ khí', 'weapon', 'quân sự', 'military', 'tên lửa', 'missile', 'máy bay chiến đấu'],
            
            # THIÊN TAI - Mở rộng
            'thiên tai': ['thiên tai', 'natural disaster', 'thảm họa', 'disaster', 'khẩn cấp', 'emergency', 'cứu hộ', 'rescue', 'bão', 'storm', 'lũ lụt', 'flood', 'động đất', 'earthquake'],
            'động đất': ['động đất', 'earthquake', 'dư chấn', 'tâm chấn', 'địa chấn', 'richter', 'thiên tai'],
            'lũ lụt': ['lũ lụt', 'flood', 'ngập lụt', 'nước lũ', 'mưa lớn', 'thiên tai'],
            'bão': ['bão', 'storm', 'typhoon', 'siêu bão', 'gió mạnh', 'thiên tai'],
            
            # CHÍNH TRỊ - Mở rộng  
            'chính trị': ['chính trị', 'politics', 'government', 'nhà nước', 'quốc hội', 'parliament', 'chính sách', 'policy', 'bộ trưởng', 'minister'],
            'bầu cử': ['bầu cử', 'election', 'vote', 'ứng cử viên', 'candidate', 'phiếu bầu', 'campaign'],
            'tổng thống': ['tổng thống', 'president', 'chính phủ', 'government', 'lãnh đạo', 'leader'],
            
            # THỂ THAO - Mở rộng
            'thể thao': ['thể thao', 'sports', 'sport', 'giải đấu', 'tournament', 'thi đấu', 'competition', 'vô địch', 'champion'],
            'bóng đá': ['bóng đá', 'football', 'soccer', 'World Cup', 'FIFA', 'premier league', 'thể thao'],
            'tennis': ['tennis', 'Wimbledon', 'US Open', 'thể thao'],
            'olympic': ['Olympic', 'Olympics', 'Thế vận hội', 'thể thao'],
            
            # MÔI TRƯỜNG - TỐI ƯU HÓA
            'môi trường': ['môi trường', 'environment', 'sinh thái', 'ecology', 'bảo tồn', 'conservation', 'ô nhiễm', 'pollution', 'khí hậu', 'climate', 'carbon', 'xanh', 'green', 'bền vững', 'sustainable', 'rác thải', 'waste', 'tái chế', 'recycle', 'năng lượng tái tạo', 'renewable energy', 'biodiversity', 'đa dạng sinh học'],
            'biến đổi khí hậu': ['biến đổi khí hậu', 'climate change', 'nóng lên toàn cầu', 'global warming', 'môi trường', 'carbon', 'khí thải', 'emissions'],
            'ô nhiễm': ['ô nhiễm', 'pollution', 'môi trường', 'khí thải', 'nước thải', 'rác thải', 'chất độc', 'toxic'],
            'năng lượng tái tạo': ['năng lượng tái tạo', 'renewable energy', 'solar', 'wind', 'điện mặt trời', 'điện gió', 'xanh', 'green energy'],
            
            # GIÁO DỤC
            'giáo dục': ['giáo dục', 'education', 'trường học', 'school', 'đại học', 'university', 'học sinh', 'student', 'giáo viên', 'teacher'],
        }
        
        # 1. Kiểm tra exact match cho topic
        if topic_lower in keyword_relations:
            related.extend(keyword_relations[topic_lower])
        
        # 2. Kiểm tra từng từ trong topic
        topic_words = topic_lower.split()
        for word in topic_words:
            if word in keyword_relations and word != topic_lower:
                related.extend(keyword_relations[word])
        
        # 3. Kiểm tra partial match
        for key, values in keyword_relations.items():
            if any(word in key for word in topic_words) or any(word in topic_lower for word in key.split()):
                related.extend(values)
        
        # 4. Thêm từ khóa đồng nghĩa tiếng Anh/Việt
        synonyms = {
            'y tế': ['healthcare', 'medical', 'health'],
            'công nghệ': ['technology', 'tech', 'innovation'],
            'kinh tế': ['economy', 'economic', 'finance'],
            'chính trị': ['politics', 'political', 'government'],
            'thể thao': ['sports', 'sport', 'athletic'],
            'quân sự': ['military', 'defense', 'army'],
            'thiên tai': ['disaster', 'natural disaster', 'emergency']
        }
        
        for viet_word, eng_words in synonyms.items():
            if viet_word in topic_lower:
                related.extend(eng_words)
            elif any(eng_word in topic_lower for eng_word in eng_words):
                related.append(viet_word)
        
        # 3. Kiểm tra partial match
        for key, values in keyword_relations.items():
            if any(word in key for word in topic_words) or any(word in topic_lower for word in key.split()):
                related.extend(values)
        
        # 4. FALLBACK cho topic không có trong dictionary - TẠO TỪ KHÓA TƯƠNG TỰ
        if not related:
            # Tạo từ khóa tương tự dựa trên cấu trúc từ
            fallback_keywords = []
            for word in topic_words:
                if len(word) > 3:
                    # Thêm từ gốc
                    fallback_keywords.append(word)
                    # Thêm các biến thể có thể
                    if word.endswith('học'):
                        fallback_keywords.extend([f'{word[:-2]}', f'{word} viện', f'{word} khoa'])
                    elif word.endswith('nghệ'):
                        fallback_keywords.extend([f'{word} số', f'{word} mới', f'{word} cao'])
                    elif word.endswith('tế'):
                        fallback_keywords.extend([f'{word} xã hội', f'{word} quốc tế', f'{word} thế giới'])
                    # Thêm các từ liên quan chung
                    fallback_keywords.extend([f'{word} Việt Nam', f'{word} mới', f'{word} 2024', f'{word} 2025'])
            
            related.extend(fallback_keywords)
        
        # 5. Loại bỏ duplicate và giới hạn
        unique_related = []
        seen = set()
        for item in related:
            if item.lower() not in seen and len(item) > 1:
                unique_related.append(item)
                seen.add(item.lower())
        
        return unique_related[:15]  # Trả về tối đa 15 từ khóa

    def search_via_sitemap(self, topic):
        """Tìm kiếm qua sitemap hoặc RSS của trang web với retry logic"""
        articles = []
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'vi-VN,vi;q=0.8,en-US;q=0.5,en;q=0.3',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive'
            }

            # Thử các URL sitemap và RSS phổ biến với retry
            sitemap_urls = [
                'https://1thegioi.vn/sitemap.xml',
                'https://1thegioi.vn/sitemap_index.xml',
                'https://1thegioi.vn/rss.xml',
                'https://1thegioi.vn/feed',
                'https://1thegioi.vn/feed.xml',
                'https://1thegioi.vn/robots.txt'
            ]

            keywords = self.extract_keywords(topic)
            seen_urls = set()

            for sitemap_url in sitemap_urls:
                if len(articles) >= 5:
                    break

                # Retry logic
                for attempt in range(3):
                    try:
                        response = requests.get(sitemap_url, headers=headers, timeout=15)

                        if response.status_code == 200:
                            # Xử lý robots.txt để tìm sitemap
                            if 'robots.txt' in sitemap_url:
                                for line in response.text.split('\n'):
                                    if line.lower().startswith('sitemap:'):
                                        real_sitemap = line.split(':', 1)[1].strip()
                                        if real_sitemap not in sitemap_urls:
                                            sitemap_urls.append(real_sitemap)
                                continue

                            # Parse XML sitemap/RSS với nhiều phương thức
                            soup = None
                            content = response.content.decode('utf-8', errors='ignore')

                            # Thử parse như XML trước
                            try:
                                from xml.etree import ElementTree as ET
                                root = ET.fromstring(content)
                                # Convert to dict for easier processing
                                soup = self.xml_to_dict(root)
                            except Exception as e:
                                # Fallback to BeautifulSoup
                                try:
                                    soup = BeautifulSoup(content, 'xml')
                                except Exception as e:
                                    try:
                                        soup = BeautifulSoup(content, 'html.parser')
                                    except Exception as e:
                                        continue

                            if soup is None:
                                continue

                            # Tìm URLs từ sitemap - hỗ trợ nhiều format
                            urls = []

                            # Kiểm tra kiểu dữ liệu của soup
                            if isinstance(soup, dict):
                                # Xử lý dict format từ xml_to_dict
                                urls = self.extract_urls_from_dict(soup)
                            elif hasattr(soup, 'find_all'):
                                # Xử lý BeautifulSoup object
                                url_tags = soup.find_all(['url', 'item', 'entry', 'link'])
                                for url_elem in url_tags:
                                    loc_elem = url_elem.find('loc') or url_elem.find('link') or url_elem
                                    if loc_elem:
                                        if hasattr(loc_elem, 'text') and loc_elem.text:
                                            url = loc_elem.text.strip()
                                        elif hasattr(loc_elem, 'get'):
                                            url = loc_elem.get('href', '')
                                        else:
                                            url = str(loc_elem).strip()
                                        if url and url.startswith('http'):
                                            urls.append((url, url_elem))
                            else:
                                continue

                            # Xử lý từng URL
                            for url_data in urls[:30]:  # Tăng lên 30 bài
                                if len(articles) >= 5:
                                    break

                                try:
                                    if isinstance(url_data, tuple):
                                        url, url_elem = url_data
                                    else:
                                        url = url_data
                                        url_elem = None

                                    if not url or url in seen_urls or '1thegioi.vn' not in url:
                                        continue

                                    # Tạo title từ URL hoặc metadata
                                    title = ""
                                    if url_elem:
                                        title_elem = url_elem.find('title') or url_elem.find('name')
                                        if title_elem and hasattr(title_elem, 'text'):
                                            title = title_elem.text.strip()

                                    if not title:
                                        title = url.split('/')[-1].replace('-', ' ').replace('.html', '').replace('_', ' ')
                                        if len(title) < 5:
                                            title = f"Bài viết về {topic}"

                                    # Kiểm tra liên quan
                                    relevance_score = self.calculate_relevance_score(title, url, topic, keywords)

                                    if relevance_score > 0.3:  # Giảm ngưỡng
                                        # Lấy nội dung bài viết
                                        content = self.get_article_content(url)

                                        if content and len(content) > 50:
                                            articles.append({
                                                'title': title.strip(),
                                                'url': url,
                                                'content': content,
                                                'relevance_score': relevance_score,
                                                'source': 'sitemap'
                                            })

                                            seen_urls.add(url)

                                except Exception as e:
                                    continue

                            break  # Thành công, thoát retry loop

                        else:
                            if attempt < 2:  # Chỉ retry nếu chưa phải lần cuối
                                time.sleep(2)
                                continue
                            else:
                                break

                    except Exception as e:
                        if attempt < 2:
                            time.sleep(2)
                            continue
                        else:
                            break

            return articles

        except Exception as e:
            return []

    def search_by_url_pattern(self, topic):
        """Tìm kiếm bằng cách đoán URL pattern dựa trên topic"""
        articles = []
        try:
            print(f"[PATTERN] Tìm kiếm bằng URL pattern cho: '{topic}'")
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            # Tạo các URL pattern có thể có
            topic_slug = topic.lower().replace(' ', '-').replace('ầ', 'a').replace('ă', 'a').replace('ê', 'e').replace('ô', 'o').replace('ơ', 'o').replace('ư', 'u')
            
            # Các pattern URL phổ biến
            url_patterns = [
                f"https://1thegioi.vn/{topic_slug}",
                f"https://1thegioi.vn/thoi-su/{topic_slug}",
                f"https://1thegioi.vn/ca-phe-mot-the-gioi/{topic_slug}",
                f"https://1thegioi.vn/cong-nghe-quan-su/{topic_slug}",
                # Thử các pattern với từ khóa riêng lẻ
                f"https://1thegioi.vn/ukraine-{topic_slug}",
                f"https://1thegioi.vn/russia-{topic_slug}",
                f"https://1thegioi.vn/chien-tranh-{topic_slug}",
                # Pattern với số bài viết
                f"https://1thegioi.vn/{topic_slug}-{{}}.html",
                f"https://1thegioi.vn/{topic_slug.replace('-', '')}-{{}}.html"
            ]
            
            # Thử từng pattern
            for base_pattern in url_patterns[:5]:  # Giới hạn 5 pattern để không quá chậm
                if len(articles) >= 3:
                    break
                    
                # Nếu pattern có {}, thử với các số
                if '{}' in base_pattern:
                    for num in [1, 2, 3, 4, 5]:
                        test_url = base_pattern.format(str(num).zfill(6))  # 6 digits: 000001, 000002, etc
                        
                        try:
                            print(f"[PATTERN] Thử URL: {test_url}")
                            response = requests.head(test_url, headers=headers, timeout=5)
                            
                            if response.status_code == 200:
                                # URL tồn tại, lấy nội dung
                                full_response = requests.get(test_url, headers=headers, timeout=10)
                                if full_response.status_code == 200:
                                    soup = BeautifulSoup(full_response.content, 'html.parser')
                                    
                                    # Tìm title
                                    title_elem = soup.find('title') or soup.find('h1') or soup.find('h2')
                                    title = title_elem.get_text(strip=True) if title_elem else f"Bài viết về {topic}"
                                    
                                    # Kiểm tra liên quan
                                    keywords = self.extract_keywords(topic)
                                    score = self.calculate_relevance_score(title, test_url, topic, keywords)
                                    
                                    if score > 0:
                                        content = self.get_article_content(test_url)
                                        
                                        articles.append({
                                            'title': title,
                                            'url': test_url,
                                            'content': content,
                                            'relevance_score': score,
                                            'source': 'url_pattern'
                                        })
                                        
                                        print(f"[PATTERN] Tìm thấy (score={score:.2f}): {title[:60]}...")
                        except:
                            continue
                else:
                    # Pattern không có {}, thử trực tiếp
                    try:
                        print(f"[PATTERN] Thử URL: {base_pattern}")
                        response = requests.head(base_pattern, headers=headers, timeout=5)
                        
                        if response.status_code == 200:
                            # URL tồn tại
                            print(f"[PATTERN] URL tồn tại: {base_pattern}")
                    except:
                        continue
            
            return articles
            
        except Exception as e:
            print(f"[ERROR] Lỗi tìm kiếm URL pattern: {e}")
            return []

    def create_fallback_articles(self, topic):
        """Tạo bài viết dự phòng khi không tìm thấy kết quả"""
        return [
            {
                'title': f'Thông tin về {topic} - Cập nhật mới nhất',
                'url': 'https://1thegioi.vn/',
                'content': f'Hiện tại đang cập nhật thông tin về {topic}. Vui lòng thử lại sau.',
                'source': 'fallback'
            },
            {
                'title': f'Phân tích {topic} - Xu hướng và phát triển',
                'url': 'https://1thegioi.vn/',
                'content': f'Phân tích chi tiết về {topic} và các xu hướng phát triển liên quan.',
                'source': 'fallback'
            },
            {
                'title': f'{topic} - Tác động và ý nghĩa',
                'url': 'https://1thegioi.vn/',
                'content': f'Nghiên cứu về tác động và ý nghĩa của {topic} trong bối cảnh hiện tại.',
                'source': 'fallback'
            }
        ]

    def get_article_content(self, url):
        """Lấy nội dung bài viết"""
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Tìm nội dung trong các thẻ phổ biến trên 1thegioi.vn
                content_selectors = [
                    # Main content areas
                    '.content', '.article-content', '.post-content', '.entry-content',
                    'article .content', 'article p', '.article-body', '.post-body',

                    # Specific 1thegioi.vn patterns
                    '.article-detail', '.news-content', '.detail-content',
                    '.main-content', '.article-text', '.news-text',

                    # Generic content selectors
                    '.text', '.description', '.summary', '.excerpt',
                    'p', '.paragraph', '.content p',

                    # Fallback selectors
                    '[class*="content"]', '[class*="article"]', '[class*="post"]'
                ]

                content = ""
                for selector in content_selectors:
                    elements = soup.select(selector)
                    if elements:
                        # Lấy text từ các elements, ưu tiên paragraphs
                        text_parts = []
                        for elem in elements[:5]:  # Lấy tối đa 5 elements
                            text = elem.get_text(strip=True)
                            if len(text) > 20:  # Chỉ lấy text có ý nghĩa
                                text_parts.append(text)

                        if text_parts:
                            content = ' '.join(text_parts)
                            if len(content) > 200:  # Đảm bảo có đủ nội dung
                                break

                # Nếu không tìm thấy content, thử lấy từ toàn bộ body
                if not content or len(content) < 50:
                    body = soup.find('body')
                    if body:
                        content = body.get_text(strip=True)[:1000]

                return content[:800] if content else "Không thể lấy nội dung bài viết."
        except:
            return "Không thể truy cập nội dung bài viết."

    def summarize_with_ollama(self, topic, articles):
        """Tạo báo cáo tóm tắt chuyên nghiệp về chủ đề dựa trên các bài viết tìm được"""
        try:
            if isinstance(articles, str):
                print("⚠️  Nhận được dữ liệu không hợp lệ")
                return f"Không thể tạo báo cáo chi tiết cho chủ đề '{topic}' do dữ liệu không hợp lệ."
            
            if not articles or len(articles) == 0:
                print("⚠️  Không có bài viết để phân tích")
                return self.create_default_report(topic)
            
            print(f"📊 Đang phân tích {len(articles)} bài viết về '{topic}'...")
            
            # Chuẩn bị nội dung từ các bài viết
            articles_summary = []
            for i, article in enumerate(articles[:5], 1):
                title = article.get('title', f'Bài viết {i}')
                content = article.get('content', '')[:600]  # Giới hạn 600 ký tự
                url = article.get('url', '')
                score = article.get('relevance_score', 0)
                
                articles_summary.append(f"""
Bài {i}: {title}
Độ liên quan: {score:.1f}/10
Tóm tắt: {content}
Link: {url}
""")
            
            content_text = "\n".join(articles_summary)
            
            # Prompt tối ưu cho Ollama - yêu cầu báo cáo toàn diện
            prompt = f"""Phân tích chuyên sâu về chủ đề "{topic}" dựa trên {len(articles)} bài báo từ 1thegioi.vn:

{content_text}

YÊU CẦU PHÂN TÍCH CHI TIẾT:

1. **TÓM TẮT NỘI DUNG CHÍNH:**
   - Phân tích nội dung chính của từng bài viết (2-3 câu/bài)
   - Xác định các chủ đề phụ và khía cạnh quan trọng

2. **PHÂN TÍCH XU HƯỚNG:**
   - Xu hướng phát triển của chủ đề "{topic}"
   - Điểm nổi bật và thay đổi gần đây
   - Quan điểm của các nguồn tin

3. **ĐÁNH GIÁ TÁC ĐỘNG:**
   - Tác động đến xã hội, kinh tế, chính trị
   - Ý nghĩa đối với Việt Nam và khu vực
   - Cơ hội và thách thức

4. **KẾT LUẬN VÀ DỰ BÁO:**
   - Tổng kết các điểm chính
   - Dự báo xu hướng tương lai
   - Khuyến nghị cho người đọc

Viết bằng tiếng Việt, chuyên nghiệp, logic, dài 600-800 từ. Tập trung vào thông tin thực tế từ các bài viết."""
            
            # Gọi Ollama
            try:
                response = requests.post('http://localhost:11434/api/generate', 
                    json={
                        'model': 'gemma2:2b',  # Sử dụng model nhẹ hơn
                        'prompt': prompt,
                        'stream': False,
                        'options': {
                            'temperature': 0.7,
                            'top_p': 0.9,
                            'num_predict': 800
                        }
                    },
                    timeout=90
                )
                
                if response.status_code == 200:
                    result = response.json()
                    ollama_response = result.get('response', '').strip()
                    
                    if ollama_response and len(ollama_response) > 150:
                        print("✅ Đã tạo báo cáo phân tích bằng AI")
                        
                        # Tạo báo cáo hoàn chỉnh với thông tin tổng quát
                        topic_overview = self.analyze_topic(topic, articles)
                        topic_aspects = self.get_topic_aspects(topic)
                        topic_impact = self.get_topic_impact(topic)
                        related_topics = self.get_related_topics(topic)

                        final_report = f"""# 📋 BÁO CÁO PHÂN TÍCH CHI TIẾT: {topic.upper()}

**🕒 Thời gian:** {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
**📊 Số bài viết phân tích:** {len(articles)}
**🌐 Nguồn:** 1thegioi.vn
**🤖 Phân tích:** AI (Ollama)

---

## 🎯 TỔNG QUAN VỀ CHỦ ĐỀ

{topic_overview}

### 📊 THỐNG KÊ:
- **Tổng số bài viết:** {len(articles)} bài viết liên quan
- **Độ liên quan cao nhất:** {max((a.get('relevance_score', 0) for a in articles), default=0):.1f}/10
- **Độ liên quan trung bình:** {sum(a.get('relevance_score', 0) for a in articles) / len(articles):.1f}/10

---

## 📖 PHÂN TÍCH CHI TIẾT

{ollama_response}

---

## 🔍 CÁC KHÍA CẠNH CHÍNH

{topic_aspects}

---

## � Ý NGHĨA VÀ TÁC ĐỘNG

{topic_impact}

---

## �📰 CÁC BÀI VIẾT THAM KHẢO

""" + "\n".join([f"**{i+1}.** [{art.get('title', 'Không có tiêu đề')}]({art.get('url', '#')})\n    *Độ liên quan: {art.get('relevance_score', 0):.1f}/10*" 
                                for i, art in enumerate(articles[:5])]) + f"""

---

## 🔗 CHỦ ĐỀ LIÊN QUAN

{related_topics}

---
*Báo cáo được tạo bởi Chatbot 1thegioi.vn với hỗ trợ AI*
*Tạo ngày: {datetime.now().strftime('%d/%m/%Y')} | Phiên bản: 2.0*"""

                        return final_report
                    else:
                        print("⚠️  AI trả về nội dung quá ngắn")
                else:
                    print(f"❌ Ollama lỗi HTTP {response.status_code}")
                    
            except requests.exceptions.Timeout:
                print("⏰ Ollama timeout - tạo báo cáo thủ công")
            except requests.exceptions.ConnectionError:
                print("🔌 Không kết nối được Ollama - tạo báo cáo thủ công")
            except Exception as e:
                print(f"❌ Lỗi Ollama: {e}")
        
        except Exception as e:
            print(f"❌ Lỗi tạo báo cáo với AI: {e}")
        
        # Fallback - luôn tạo báo cáo thủ công chi tiết
        print("📝 Tạo báo cáo thủ công chi tiết...")
        return self.create_manual_report(topic, articles)

    def create_manual_report(self, topic, articles):
        """Tạo báo cáo tóm tắt toàn diện với thông tin tổng quát về chủ đề"""
        print("📝 Đang tạo báo cáo tổng quát chi tiết...")

        if not articles:
            return self.create_default_report(topic)

        # Đảm bảo chỉ lấy 3 bài liên quan nhất
        top_articles = articles[:3]

        # Phân tích chủ đề để tạo tóm tắt tổng quan
        topic_analysis = self.analyze_topic(topic, top_articles)

        # Phân tích nguồn
        sources_count = {}
        for article in top_articles:
            source = article.get('source', 'unknown')
            if '1thegioi.vn' in article.get('url', ''):
                source = '1thegioi.vn'
            sources_count[source] = sources_count.get(source, 0) + 1

        sources_summary = ", ".join([f"{source}: {count}" for source, count in sources_count.items()])

        # Tạo tóm tắt nội dung cho từng bài
        article_summaries = []
        for i, article in enumerate(top_articles, 1):
            title = article.get('title', 'Bài viết không có tiêu đề')
            url = article.get('url', 'N/A')
            content = article.get('content', '')
            score = article.get('relevance_score', 0)
            source = article.get('source', 'unknown')

            # Xác định loại nguồn
            if '1thegioi.vn' in url:
                source_display = "📰 1thegioi.vn"
                source_badge = "⭐ Nguồn chính"
            else:
                source_display = f"🌐 {source}"
                source_badge = "📌 Nguồn bổ sung"

            # Tóm tắt nội dung (lấy 300 ký tự đầu)
            summary = content[:300] + "..." if len(content) > 300 else content
            if not summary:
                summary = "Không có nội dung chi tiết"

            article_summaries.append(f"""
### {i}. {title}
**🔗 Nguồn:** {source_display} | {source_badge}
**📍 URL:** {url}
**⭐ Độ liên quan:** {score:.1f}/10
**📄 Tóm tắt:** {summary}""")

        # Tạo thống kê bổ sung
        total_articles_found = len(articles)
        avg_relevance = sum(a.get('relevance_score', 0) for a in top_articles) / len(top_articles) if top_articles else 0

        report = f"""# 📋 BÁO CÁO TỔNG QUAN CHI TIẾT: {topic.upper()}

**🕒 Thời gian tạo:** {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
**📊 Số bài viết phân tích:** {len(top_articles)}/{total_articles_found}
**🌐 Nguồn tin:** {sources_summary}
**📈 Độ liên quan trung bình:** {avg_relevance:.1f}/10

---

## 🎯 TỔNG QUAN VỀ CHỦ ĐỀ "{topic}"

{topic_analysis}

### 📊 THỐNG KÊ CHÍNH:
- **Tổng số bài viết tìm thấy:** {total_articles_found} bài viết liên quan
- **Phân bố nguồn:** {sources_summary}
- **Độ liên quan cao nhất:** {max((a.get('relevance_score', 0) for a in top_articles), default=0):.1f}/10
- **Độ liên quan thấp nhất:** {min((a.get('relevance_score', 0) for a in top_articles), default=0):.1f}/10

---

## 📖 PHÂN TÍCH CHI TIẾT CÁC BÀI VIẾT

Dựa trên phân tích từ trang tin tức uy tín 1thegioi.vn, dưới đây là {len(top_articles)} bài viết liên quan trực tiếp và có chất lượng cao nhất đến chủ đề "{topic}":

{"".join(article_summaries)}

---

## 🔍 PHÂN TÍCH SÂU HƠN

### 🌟 ĐIỂM MẠNH:
- Các bài viết được chọn lọc kỹ lưỡng dựa trên độ liên quan nội dung
- Thông tin cập nhật từ nguồn tin tức chính thống và uy tín
- Bao phủ nhiều khía cạnh khác nhau của chủ đề

### 📋 CÁC KHÍA CẠNH CHÍNH:
{self.get_topic_aspects(topic)}

### 💡 Ý NGHĨA VÀ TÁC ĐỘNG:
{self.get_topic_impact(topic)}

---

## 🎯 KẾT LUẬN VÀ KHUYẾN NGHỊ

### ✅ KẾT LUẬN:
Thông tin về chủ đề "{topic}" đang được quan tâm rộng rãi trên các phương tiện truyền thông. Các bài viết phân tích cho thấy sự phát triển và thay đổi liên tục trong lĩnh vực này.

### 📋 KHUYẾN NGHỊ:
- Theo dõi thêm các nguồn tin tức uy tín để cập nhật thông tin mới nhất
- Tham khảo ý kiến chuyên gia trong lĩnh vực liên quan
- Áp dụng thông tin một cách có chọn lọc và phù hợp với hoàn cảnh cụ thể

### 🔗 THÔNG TIN THAM KHẢO THÊM:
- Website chính thức: https://1thegioi.vn/
- Các chủ đề liên quan: {self.get_related_topics(topic)}

---

*Báo cáo được tạo tự động bởi Chatbot 1thegioi.vn*
*Tạo ngày: {datetime.now().strftime('%d/%m/%Y')} | Phiên bản: 2.0*"""

        return report

    def create_default_report(self, topic):
        """Tạo báo cáo mặc định với thông tin tổng quát khi không tìm thấy bài viết"""
        topic_analysis = self.analyze_topic(topic, [])

        return f"""# 📋 BÁO CÁO TỔNG QUAN: {topic.upper()}

**🕒 Thời gian:** {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
**📊 Kết quả:** Đang cập nhật thông tin
**🌐 Nguồn:** 1thegioi.vn

## 🎯 TỔNG QUAN VỀ CHỦ ĐỀ

{topic_analysis}

## 📖 THÔNG TIN HIỆN TẠI

Hiện tại chưa tìm thấy bài viết cụ thể về chủ đề "{topic}" trên 1thegioi.vn. Tuy nhiên, đây là một chủ đề quan trọng và đang được quan tâm rộng rãi.

### 📊 CÁC KHÍA CẠNH CHÍNH:
{self.get_topic_aspects(topic)}

### 💡 Ý NGHĨA VÀ TÁC ĐỘNG:
{self.get_topic_impact(topic)}

## 💡 GỢI Ý TÌM KIẾM:

### 🔍 Từ khóa thay thế:
- Thử sử dụng từ khóa tiếng Việt hoặc tiếng Anh
- Sử dụng từ khóa cụ thể hơn hoặc tổng quát hơn
- Kiểm tra lại chính tả và dấu cách

### � TÌM KIẾM MỞ RỘNG TỰ ĐỘNG:
- **Tìm kiếm web tổng quát:** Hệ thống sẽ tự động tìm kiếm trên toàn bộ internet nếu không tìm thấy trên 1thegioi.vn
- **Nguồn đa dạng:** Bao gồm các trang tin tức uy tín như VNExpress, Tuổi Trẻ, Thanh Niên, VTV, Dân Trí, etc.
- **Chất lượng đảm bảo:** Chỉ chọn lọc các bài viết có độ liên quan cao và từ nguồn tin cậy
- **Phạm vi rộng:** Khả năng tìm kiếm bất kỳ chủ đề nào, không giới hạn trong chuyên mục của 1thegioi.vn

### � Chủ đề liên quan:
{self.get_related_topics(topic)}

## 🎯 KHUYẾN NGHỊ:

1. **Theo dõi thường xuyên:** Chủ đề này có thể có bài viết mới trong thời gian tới
2. **Mở rộng tìm kiếm:** Thử tìm kiếm với các từ khóa liên quan
3. **Đăng ký nhận tin:** Theo dõi 1thegioi.vn để nhận thông tin cập nhật
4. **Tham khảo nguồn khác:** Có thể tìm kiếm trên các trang tin tức uy tín khác

---
*Báo cáo được tạo bởi Chatbot 1thegioi.vn*
*Tạo ngày: {datetime.now().strftime('%d/%m/%Y')} | Phiên bản: 2.0*

*💡 Mẹo: Hãy thử lại sau vài giờ hoặc sử dụng từ khóa khác để có kết quả tốt hơn!*"""

    @agent
    def greeter(self) -> Agent:
        return Agent(
            config=self.agents_config['greeter'],
            verbose=True
        )
    
    @agent  
    def controller(self) -> Agent:
        return Agent(
            config=self.agents_config['controller'],
            verbose=True
        )
    
    @agent
    def category_provider(self) -> Agent:
        return Agent(
            config=self.agents_config['category_provider'],
            verbose=True
        )
    
    @agent
    def search_summarizer(self) -> Agent:
        return Agent(
            config=self.agents_config['search_summarizer'], 
            verbose=True
        )

    @task
    def greet_task(self) -> Task:
        return Task(
            config=self.tasks_config['greet_task']
        )
    
    @task
    def control_task(self) -> Task:
        return Task(
            config=self.tasks_config['control_task']
        )
    
    @task
    def category_task(self) -> Task:
        return Task(
            config=self.tasks_config['category_task']
        )
    
    @task
    def search_summary_task(self) -> Task:
        return Task(
            config=self.tasks_config['search_summary_task']
        )

    def analyze_topic(self, topic, articles):
        """Phân tích tổng quan về chủ đề dựa trên các bài viết"""
        topic_lower = topic.lower()

        # Phân tích theo loại chủ đề
        if any(term in topic_lower for term in ['quân sự', 'military', 'chiến tranh', 'vũ khí']):
            return f"""**Quân sự và Quốc phòng** là lĩnh vực quan trọng trong bối cảnh quốc tế hiện nay. Các bài viết phân tích cho thấy sự phát triển nhanh chóng của công nghệ quân sự, các xung đột địa chính trị, và vai trò của các cường quốc trong việc duy trì an ninh toàn cầu. Thông tin từ 1thegioi.vn cung cấp cái nhìn sâu sắc về các vấn đề quân sự từ góc độ Việt Nam và khu vực."""

        elif any(term in topic_lower for term in ['công nghệ', 'technology', 'ai', 'blockchain']):
            return f"""**Công nghệ và Đổi mới** đang định hình tương lai của nhân loại. Các bài viết tập trung vào sự phát triển của trí tuệ nhân tạo, công nghệ blockchain, và các xu hướng công nghệ mới. 1thegioi.vn cung cấp thông tin cập nhật về các tiến bộ công nghệ và tác động của chúng đến xã hội."""

        elif any(term in topic_lower for term in ['kinh tế', 'economy', 'tài chính']):
            return f"""**Kinh tế và Tài chính** là động lực phát triển của mỗi quốc gia. Các bài viết phân tích về tăng trưởng kinh tế, thị trường tài chính, và các chính sách kinh tế. Thông tin từ 1thegioi.vn giúp người đọc hiểu rõ hơn về tình hình kinh tế trong nước và quốc tế."""

        elif any(term in topic_lower for term in ['chính trị', 'politics', 'bầu cử']):
            return f"""**Chính trị và Xã hội** ảnh hưởng trực tiếp đến đời sống của người dân. Các bài viết đề cập đến các vấn đề chính trị, chính sách xã hội, và các sự kiện chính trị quan trọng. 1thegioi.vn cung cấp góc nhìn đa chiều về các vấn đề chính trị."""

        elif any(term in topic_lower for term in ['thể thao', 'sports']):
            return f"""**Thể thao** là lĩnh vực giải trí và rèn luyện sức khỏe phổ biến. Các bài viết cập nhật về các giải đấu, thành tích của vận động viên, và các sự kiện thể thao quốc tế. 1thegioi.vn mang đến thông tin thể thao đa dạng."""

        elif any(term in topic_lower for term in ['y tế', 'health', 'covid']):
            return f"""**Y tế và Sức khỏe** là vấn đề thiết yếu của mỗi người. Các bài viết đề cập đến các vấn đề y tế công cộng, tiến bộ y học, và chăm sóc sức khỏe. 1thegioi.vn cung cấp thông tin y tế đáng tin cậy."""

        else:
            return f"""**{topic}** là chủ đề đang được quan tâm trong xã hội hiện đại. Các bài viết từ 1thegioi.vn cung cấp thông tin đa chiều về chủ đề này, giúp người đọc có cái nhìn toàn diện và sâu sắc hơn."""

    def get_topic_aspects(self, topic):
        """Lấy các khía cạnh chính của chủ đề"""
        topic_lower = topic.lower()

        aspects = {
            'quân sự': [
                "• Công nghệ quân sự hiện đại",
                "• Chiến lược quốc phòng",
                "• Quan hệ quốc tế",
                "• An ninh khu vực",
                "• Phát triển vũ khí"
            ],
            'công nghệ': [
                "• Trí tuệ nhân tạo (AI)",
                "• Công nghệ số",
                "• Blockchain và tiền mã hóa",
                "• Đổi mới sáng tạo",
                "• Tác động xã hội"
            ],
            'kinh tế': [
                "• Tăng trưởng kinh tế",
                "• Thị trường tài chính",
                "• Chính sách kinh tế",
                "• Thương mại quốc tế",
                "• Đầu tư và phát triển"
            ],
            'chính trị': [
                "• Chính sách đối nội",
                "• Quan hệ quốc tế",
                "• Các vấn đề xã hội",
                "• Bầu cử và dân chủ",
                "• Phát triển bền vững"
            ],
            'thể thao': [
                "• Các giải đấu quốc tế",
                "• Thành tích vận động viên",
                "• Phát triển thể thao",
                "• Sự kiện thể thao",
                "• Tác động văn hóa"
            ],
            'y tế': [
                "• Y tế công cộng",
                "• Tiến bộ y học",
                "• Chăm sóc sức khỏe",
                "• Phòng ngừa bệnh tật",
                "• Chính sách y tế"
            ]
        }

        # Tìm khía cạnh phù hợp
        for key, value in aspects.items():
            if key in topic_lower:
                return "\n".join(value)

        # Khía cạnh chung cho chủ đề khác
        return """• Phát triển và xu hướng
• Tác động đến xã hội
• Quan điểm chuyên gia
• Thực trạng hiện tại
• Hướng phát triển tương lai"""

    def get_topic_impact(self, topic):
        """Lấy ý nghĩa và tác động của chủ đề"""
        topic_lower = topic.lower()

        impacts = {
            'quân sự': "Các vấn đề quân sự ảnh hưởng trực tiếp đến an ninh quốc gia và ổn định khu vực. Việc theo dõi các diễn biến quân sự giúp hiểu rõ hơn về tình hình quốc tế và định hướng chính sách quốc phòng.",
            'công nghệ': "Công nghệ đang thay đổi cách chúng ta sống, làm việc và tương tác. Việc cập nhật thông tin công nghệ giúp nắm bắt cơ hội và thích ứng với sự thay đổi nhanh chóng của xã hội số.",
            'kinh tế': "Tình hình kinh tế ảnh hưởng đến đời sống của mỗi người dân. Việc theo dõi các chỉ số kinh tế giúp đưa ra quyết định tài chính và đầu tư phù hợp.",
            'chính trị': "Các vấn đề chính trị định hình chính sách và pháp luật của quốc gia. Việc nắm bắt thông tin chính trị giúp công dân tham gia tích cực vào các vấn đề xã hội.",
            'thể thao': "Thể thao góp phần nâng cao sức khỏe và tinh thần của người dân. Các hoạt động thể thao còn tạo nên bản sắc văn hóa và tinh thần đoàn kết dân tộc.",
            'y tế': "Sức khỏe là tài sản quý giá nhất của con người. Việc nâng cao nhận thức về y tế giúp phòng ngừa bệnh tật và cải thiện chất lượng cuộc sống."
        }

        # Tìm tác động phù hợp
        for key, value in impacts.items():
            if key in topic_lower:
                return value

        # Tác động chung
        return f"Chủ đề '{topic}' có ý nghĩa quan trọng trong việc nâng cao nhận thức và kiến thức của cộng đồng. Việc theo dõi và cập nhật thông tin giúp chúng ta có cái nhìn toàn diện và sâu sắc hơn về các vấn đề xã hội."

    def get_related_topics(self, topic):
        """Lấy các chủ đề liên quan"""
        topic_lower = topic.lower()

        related_topics = {
            'quân sự': "Công nghệ quân sự, An ninh quốc gia, Quan hệ quốc tế, Chiến lược quốc phòng",
            'công nghệ': "AI & Machine Learning, Blockchain, IoT, Công nghệ 4.0, Số hóa",
            'kinh tế': "Tài chính, Đầu tư, Thương mại, Phát triển bền vững, Thị trường lao động",
            'chính trị': "Chính sách xã hội, Quan hệ quốc tế, Phát triển bền vững, Dân chủ",
            'thể thao': "Sức khỏe, Giáo dục thể chất, Sự kiện quốc tế, Văn hóa thể thao",
            'y tế': "Sức khỏe cộng đồng, Y học hiện đại, Phòng ngừa bệnh tật, Chăm sóc sức khỏe"
        }

        # Tìm chủ đề liên quan phù hợp
        for key, value in related_topics.items():
            if key in topic_lower:
                return value

        # Chủ đề liên quan chung
        return f"Các chủ đề liên quan đến {topic}, Phát triển xã hội, Xu hướng hiện đại"

    def search_via_google_general(self, topic):
        """Tìm kiếm trên toàn bộ web với nhiều kỹ thuật bypass Google blocking"""
        articles = []
        try:
            print(f"🔍 Đang tìm kiếm '{topic}' trên toàn bộ web...")

            # User-Agent rotation để tránh bị chặn
            user_agents = [
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36 Edg/118.0.2088.46'
            ]

            # Các query tìm kiếm đa dạng hơn
            search_queries = [
                f'"{topic}" tin tức',
                f'{topic} 2024 2025',
                f'{topic} phân tích',
                f'{topic} xu hướng',
                f'{topic} cập nhật mới nhất',
                f'{topic} thông tin chi tiết'
            ]

            seen_urls = set()

            for i, query in enumerate(search_queries[:4]):  # Tăng lên 4 queries
                try:
                    # Rotate User-Agent
                    headers = {
                        'User-Agent': user_agents[i % len(user_agents)],
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                        'Accept-Language': 'vi-VN,vi;q=0.8,en-US;q=0.5,en;q=0.3',
                        'Accept-Encoding': 'gzip, deflate, br',
                        'DNT': '1',
                        'Connection': 'keep-alive',
                        'Upgrade-Insecure-Requests': '1',
                        'Cache-Control': 'max-age=0',
                        'Sec-Fetch-Dest': 'document',
                        'Sec-Fetch-Mode': 'navigate',
                        'Sec-Fetch-Site': 'none',
                        'Sec-Fetch-User': '?1'
                    }

                    # Tạo URL Google search với parameters mới
                    encoded_query = urllib.parse.quote_plus(query)
                    google_url = f"https://www.google.com/search?q={encoded_query}&num=15&hl=vi&safe=off&filter=0"

                    print(f"[WEB-{i+1}] Đang tìm kiếm: {query}")
                    response = requests.get(google_url, headers=headers, timeout=30)

                    print(f"[WEB-{i+1}] HTTP Status: {response.status_code}")

                    if response.status_code == 200:
                        # Kiểm tra xem có bị chặn không
                        if "Our systems have detected unusual traffic" in response.text:
                            print("[WEB] ⚠️ Bị chặn unusual traffic - thử cách khác")
                            time.sleep(5)
                            continue
                        elif "429" in response.text or "rate limit" in response.text.lower():
                            print("[WEB] ⚠️ Rate limited - đợi 10 giây")
                            time.sleep(10)
                            continue

                        soup = BeautifulSoup(response.content, 'html.parser')

                        # Thử nhiều selectors mới nhất 2024-2025
                        selectors = [
                            'div[data-ved]', 'div.tF2Cxc', 'div.MjjYud', 'div.yuRUbf',
                            'div.kCrYT', 'div.g', 'div[data-hveid]', 'div[data-ctid]',
                            'div.egMi0', 'div.Gx5Zad', 'div.IsZvec',
                            # Mobile selectors
                            'div[data-snf]', 'div[data-ved] div', 'div.tF2Cxc div',
                            'div.MjjYud div', 'div.yuRUbf div', 'div.kCrYT div',
                            # Alternative patterns
                            '.srg .g', '.srg div[data-ved]', '.srg .tF2Cxc',
                            '.srg .MjjYud', '.srg .yuRUbf', '.srg .kCrYT',
                            # New 2024 patterns
                            'div.N54PNb', 'div.kb0PBd', 'div.Ww4FFb', 'div.cfSxFb'
                        ]

                        search_results = []
                        for selector in selectors:
                            search_results = soup.select(selector)
                            if search_results:
                                print(f"[WEB] ✅ Selector '{selector}' tìm thấy {len(search_results)} kết quả")
                                break

                        print(f"[WEB] Tổng số kết quả tiềm năng: {len(search_results)}")

                        results_found = 0
                        for result in search_results[:15]:  # Tăng lên 15 kết quả
                            if len(articles) >= 8:  # Giới hạn 8 bài
                                break

                            try:
                                # Tìm title với nhiều cách hơn
                                title = ""
                                title_selectors = ['h2', 'a', '.b_title', '.title']
                                for title_sel in title_selectors:
                                    title_elem = result.select_one(title_sel)
                                    if title_elem:
                                        title = title_elem.get_text().strip()
                                        if len(title) > 5:
                                            break

                                # Tìm URL với nhiều cách hơn
                                url = ""
                                url_elem = result.select_one('a[href]')
                                if url_elem:
                                    url = url_elem.get('href', '')

                                # Xử lý URL Google redirect
                                if url.startswith('/url?q='):
                                    url = urllib.parse.unquote(url.split('/url?q=')[1].split('&')[0])
                                elif url.startswith('http://www.google.com/url?q='):
                                    url = urllib.parse.unquote(url.split('http://www.google.com/url?q=')[1].split('&')[0])

                                # Kiểm tra URL hợp lệ
                                if not title or not url or not url.startswith('http'):
                                    continue

                                # Bỏ qua các URL không liên quan (mở rộng danh sách)
                                skip_domains = [
                                    'google.com', 'youtube.com', 'facebook.com', 'ads',
                                    'javascript:', 'policies.google.com', 'support.google.com',
                                    'accounts.google.com', 'mail.google.com', 'drive.google.com'
                                ]
                                if any(skip in url.lower() for skip in skip_domains):
                                    continue

                                if url in seen_urls:
                                    continue

                                seen_urls.add(url)

                                # Tìm snippet/description với nhiều selectors hơn
                                content = ""
                                content_selectors = [
                                    'span.aCOpRe', 'div.VwiC3b', 'div.MUxGbd', 'div[data-ved] span',
                                    'div.tF2Cxc span', 'div.MjjYud span', '.aCOpRe', '.VwiC3b'
                                ]
                                for content_sel in content_selectors:
                                    content_elem = result.select_one(content_sel)
                                    if content_elem:
                                        content = content_elem.get_text().strip()
                                        if len(content) > 10:
                                            break

                                # Tính điểm liên quan (giảm ngưỡng hơn nữa)
                                relevance_score = self.calculate_relevance_score(title, url, topic, self.extract_keywords(topic))

                                # Ngưỡng rất thấp để có nhiều kết quả
                                if relevance_score >= 1.0:
                                    # Lấy nội dung bài viết nếu có thể
                                    article_content = self.get_article_content(url)
                                    if not article_content:
                                        article_content = content

                                    article = {
                                        'title': title,
                                        'url': url,
                                        'content': article_content,
                                        'source': url.split('/')[2] if '/' in url else 'web',
                                        'relevance_score': relevance_score,
                                        'search_type': 'web_general'
                                    }
                                    articles.append(article)
                                    results_found += 1
                                    print(f"[WEB] ✅ Thêm bài viết: {title[:50]}... (điểm: {relevance_score:.1f})")

                            except Exception as e:
                                continue

                        print(f"[WEB] Query {i+1} tìm thấy {results_found} bài viết")

                    else:
                        print(f"[WEB] HTTP Error {response.status_code}")
                        if response.status_code == 429:
                            print("[WEB] Rate limited - đợi 15 giây")
                            time.sleep(15)

                    # Thêm delay giữa các requests để tránh bị chặn
                    time.sleep(2)

                except Exception as e:
                    print(f"[WEB] Lỗi khi tìm kiếm query '{query}': {e}")
                    continue

            # Thử tìm kiếm từ Bing nếu Google không hoạt động
            if len(articles) < 3:
                print("[WEB] 🔄 Thử tìm kiếm từ Bing...")
                bing_articles = self.search_via_bing(topic)
                if bing_articles:
                    # Lọc trùng lặp
                    for article in bing_articles:
                        if article.get('url', '') not in seen_urls:
                            articles.append(article)
                            seen_urls.add(article.get('url', ''))

            # Thử tìm kiếm từ DuckDuckGo nếu vẫn chưa đủ
            if len(articles) < 3:
                print("[WEB] 🔄 Thử tìm kiếm từ DuckDuckGo...")
                ddg_articles = self.search_via_duckduckgo(topic)
                if ddg_articles:
                    # Lọc trùng lặp
                    for article in ddg_articles:
                        if article.get('url', '') not in seen_urls:
                            articles.append(article)
                            seen_urls.add(article.get('url', ''))

            # Sắp xếp theo điểm liên quan
            articles = sorted(articles, key=lambda x: x.get('relevance_score', 0), reverse=True)

            if articles:
                print(f"✅ Tìm thấy {len(articles)} bài viết liên quan từ web tổng quát")

            return articles[:6]  # Trả về tối đa 6 bài

        except Exception as e:
            print(f"❌ Lỗi tìm kiếm web tổng quát: {e}")
            return []

    def search_via_bing(self, topic):
        """Tìm kiếm trên Bing như phương pháp backup khi Google bị chặn"""
        articles = []
        try:
            print(f"🔍 Đang tìm kiếm '{topic}' trên Bing...")

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'vi-VN,vi;q=0.8,en-US;q=0.5,en;q=0.3',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }

            # Query cho Bing
            query = f'"{topic}" tin tức'
            encoded_query = urllib.parse.quote_plus(query)
            bing_url = f"https://www.bing.com/search?q={encoded_query}&count=15&setlang=vi"

            response = requests.get(bing_url, headers=headers, timeout=20)

            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')

                # Selectors cho Bing search results
                selectors = [
                    '.b_algo', '.b_algo h2', '.b_algo .b_title',
                    'li.b_algo', 'li.b_algo h2', 'li.b_algo .b_title',
                    '.result', '.result h2', '.result .title'
                ]

                search_results = []
                for selector in selectors:
                    search_results = soup.select(selector)
                    if search_results:
                        print(f"[BING] ✅ Selector '{selector}' tìm thấy {len(search_results)} kết quả")
                        break

                print(f"[BING] Tổng số kết quả tiềm năng: {len(search_results)}")

                results_found = 0
                for result in search_results[:10]:
                    if len(articles) >= 5:
                        break

                    try:
                        # Tìm title
                        title = ""
                        title_selectors = ['h2', 'a', '.b_title', '.title']
                        for title_sel in title_selectors:
                            title_elem = result.select_one(title_sel)
                            if title_elem:
                                title = title_elem.get_text().strip()
                                if len(title) > 5:
                                    break

                        # Tìm URL
                        url = ""
                        url_elem = result.select_one('a[href]')
                        if url_elem:
                            url = url_elem.get('href', '')

                        # Validate dữ liệu
                        if not title or not url or not url.startswith('http'):
                            continue

                        # Bỏ qua các URL không liên quan
                        skip_domains = ['bing.com', 'microsoft.com', 'youtube.com', 'facebook.com']
                        if any(skip in url.lower() for skip in skip_domains):
                            continue

                        # Tìm snippet
                        content = ""
                        content_selectors = ['.b_caption p', '.b_snippet', 'p', '.snippet']
                        for content_sel in content_selectors:
                            content_elem = result.select_one(content_sel)
                            if content_elem:
                                content = content_elem.get_text().strip()
                                if len(content) > 10:
                                    break

                        # Tính điểm liên quan
                        relevance_score = self.calculate_relevance_score(title, url, topic, self.extract_keywords(topic))

                        if relevance_score >= 1.5:  # Ngưỡng thấp hơn cho Bing
                            article = {
                                'title': title,
                                'url': url,
                                'content': content,
                                'source': url.split('/')[2] if '/' in url else 'bing',
                                'relevance_score': relevance_score,
                                'search_type': 'bing'
                            }
                            articles.append(article)
                            results_found += 1
                            print(f"[BING] ✅ Thêm bài viết: {title[:50]}... (điểm: {relevance_score:.1f})")

                    except Exception as e:
                        continue

                print(f"[BING] Tìm thấy {results_found} bài viết")

            else:
                print(f"[BING] HTTP Error {response.status_code}")

            return articles

        except Exception as e:
            print(f"❌ Lỗi tìm kiếm Bing: {e}")
            return []