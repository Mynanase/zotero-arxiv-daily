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
    """保存 RSS Feed 到文件，使用 Atom 格式并添加自定义元素
    
    添加的自定义元素：
    - dc:source: 用于存储翻译标题，被 Zotero 识别为来源信息
    - rights: 用于存储星级评分，被 Zotero 识别为权利信息
    """
    try:
        # 确保目标目录存在
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # 生成标准的 Atom feed
        feed_generator.atom_file(output_path)
        
        # 读取生成的文件
        with open(output_path, 'r', encoding='utf-8') as f:
            atom_xml = f.read()
        
        # 添加 Dublin Core 命名空间声明
        if 'xmlns:dc="http://purl.org/dc/elements/1.1/"' not in atom_xml:
            atom_xml = atom_xml.replace('<feed ', '<feed xmlns:dc="http://purl.org/dc/elements/1.1/" ')
        
        # 收集并添加自定义元素
        modified = False
        
        for entry in feed_generator.entry():
            elements = []
            arxiv_id = entry.id().split('/')[-1]
            
            # 添加翻译标题（使用 dc:source）
            if hasattr(entry, '_translated_title') and entry._translated_title:
                elements.append(f"<dc:source>{entry._translated_title}</dc:source>")
            
            # 添加星级评分（使用 rights）
            if hasattr(entry, '_relevance_score') and entry._relevance_score is not None:
                star_count = get_star_rating(entry._relevance_score)
                if star_count > 0:
                    star_rating = "⭐" * star_count
                    elements.append(f"<rights>{star_rating}</rights>")
            
            # 如果有自定义元素，插入到条目中
            if elements:
                modified = True
                entry_pattern = f"<id>http://arxiv.org/abs/{arxiv_id}</id>"
                entry_end_tag = "</entry>"
                
                start_pos = atom_xml.find(entry_pattern)
                if start_pos == -1:
                    continue
                
                end_pos = atom_xml.find(entry_end_tag, start_pos)
                if end_pos == -1:
                    continue
                
                custom_xml = "\n  " + "\n  ".join(elements)
                atom_xml = atom_xml[:end_pos] + custom_xml + atom_xml[end_pos:]
        
        # 如果有修改，将更新后的内容写回文件
        if modified:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(atom_xml)
        
        logger.info(f"RSS feed saved to {output_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to save RSS feed: {e}")
        return False
