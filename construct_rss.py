from paper import ArxivPaper
from feedgen.feed import FeedGenerator
import os
import datetime
from loguru import logger
from utils import get_star_rating

def create_feed_generator(
    title="ArXiv Daily Papers",
    link="https://arxiv.org/",
    description="Daily arXiv paper recommendations based on your Zotero library",
    feed_url=None
):
    """创建 Atom 格式的 Feed 生成器"""
    fg = FeedGenerator()
    fg.id(link)
    fg.title(title)
    fg.subtitle(description)
    fg.author({"name": "Zotero ArXiv Daily", "email": "noreply@example.com"})
    fg.language("en")
    fg.link(href=link, rel="alternate")
    
    # 添加 feed 自引用链接
    if feed_url:
        fg.link(href=feed_url, rel="self")
    
    # 设置最后更新时间（带时区信息）
    try:
        # Python 3.9+ 使用 datetime.datetime.now().astimezone()
        fg.updated(datetime.datetime.now().astimezone())
    except ValueError:
        # 如果上面的方法失败，尝试使用 UTC 时间
        fg.updated(datetime.datetime.now(datetime.timezone.utc))
    
    return fg

def add_paper_to_feed(fg, paper: ArxivPaper):
    """将论文添加到 Feed 中，格式与 arXiv 官方格式兼容"""
    entry = fg.add_entry()
    
    # 基本信息
    entry.id(f"http://arxiv.org/abs/{paper.arxiv_id}")
    entry.title(paper.title)
    
    # 添加链接
    entry.link(href=f"http://arxiv.org/abs/{paper.arxiv_id}", rel="alternate")
    entry.link(href=paper.pdf_url, rel="related", type="application/pdf", title="PDF")
    
    if paper.code_url:
        entry.link(href=paper.code_url, rel="related", title="Code")
    
    # 作者信息
    for author in paper.authors:
        entry.author(name=author.name)
    
    # 摘要和内容
    entry.summary(paper.tldr)
    
    # 将翻译和相关度信息存储在条目的自定义属性中
    if hasattr(paper, 'translated_title') and paper.translated_title:
        entry._translated_title = paper.translated_title
    
    if hasattr(paper, 'score') and paper.score is not None:
        entry._relevance_score = paper.score
    
    # 发布和更新时间
    # 使用 arxiv API 返回的论文发布和更新时间
    if hasattr(paper, 'updated'):
        entry.updated(paper.updated)
    else:
        entry.updated(datetime.datetime.now(datetime.timezone.utc))
    
    # 分类信息
    # 添加默认分类
    entry.category(term="astro-ph.GA")
    
    return entry

def render_rss(papers: list[ArxivPaper], feed_title: str = "Daily arXiv Papers", 
              feed_link: str = "https://arxiv.org/", 
              feed_description: str = "Daily arXiv paper recommendations based on your Zotero library",
              feed_url: str = None):
    """生成 RSS Feed"""
    fg = create_feed_generator(feed_title, feed_link, feed_description, feed_url)
    
    for paper in papers:
        add_paper_to_feed(fg, paper)
    
    return fg

def save_rss(feed_generator, output_path: str = "public/index.xml"):
    """保存 RSS Feed 到文件，使用 Atom 格式并添加自定义元素"""
    try:
        # 确保目标目录存在
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # 首先生成标准的 Atom feed
        feed_generator.atom_file(output_path)
        
        # 然后读取生成的文件
        with open(output_path, 'r', encoding='utf-8') as f:
            atom_xml = f.read()
        
        # 添加 zotero 命名空间声明
        if 'xmlns:zotero="http://zotero.org/ns/1.0/"' not in atom_xml:
            atom_xml = atom_xml.replace('<feed ', '<feed xmlns:zotero="http://zotero.org/ns/1.0/" ')
        
        # 准备存储每个条目的自定义元素
        custom_elements = {}
        
        # 收集所有条目的自定义元素
        for entry in feed_generator.entry():
            arxiv_id = entry.id().split('/')[-1]
            elements = []
            
            # 收集标题翻译
            if hasattr(entry, '_translated_title') and entry._translated_title:
                print(f"Adding translated title for {arxiv_id}: {entry._translated_title}")
                elements.append(f"<zotero:titleTranslation>{entry._translated_title}</zotero:titleTranslation>")
            
            # 收集相关度分数
            if hasattr(entry, '_relevance_score') and entry._relevance_score is not None:
                print(f"Adding relevance score for {arxiv_id}: {entry._relevance_score}")
                elements.append(f"<zotero:relevanceScore>{entry._relevance_score}</zotero:relevanceScore>")
                
                # 添加星级评分
                score = entry._relevance_score
                star_count = get_star_rating(score)
                if star_count > 0:
                    # 将星级数量转换为星星字符串
                    star_rating = "⭐" * star_count
                    elements.append(f"<zotero:starRating>{star_rating}</zotero:starRating>")
            
            if elements:
                custom_elements[arxiv_id] = elements
        
        # 如果没有自定义元素要添加，直接返回
        if not custom_elements:
            logger.info(f"RSS feed saved to {output_path}")
            return True
        
        # 对每个条目 ID 进行处理
        for arxiv_id, elements in custom_elements.items():
            # 定位条目
            entry_pattern = f"<id>http://arxiv.org/abs/{arxiv_id}</id>"
            entry_end_tag = "</entry>"
            
            start_pos = atom_xml.find(entry_pattern)
            if start_pos == -1:
                continue
                
            end_pos = atom_xml.find(entry_end_tag, start_pos)
            if end_pos == -1:
                continue
            
            # 在条目结束标签前插入自定义元素
            custom_xml = "\n  " + "\n  ".join(elements)
            atom_xml = atom_xml[:end_pos] + custom_xml + atom_xml[end_pos:]
        
        # 将字符串写入文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(atom_xml)
            
        logger.info(f"RSS feed saved to {output_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to save RSS feed: {e}")
        return False
