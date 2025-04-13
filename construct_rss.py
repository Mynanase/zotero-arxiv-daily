from paper import ArxivPaper
from feedgen.feed import FeedGenerator
import os
import datetime
from loguru import logger

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
    
    # 添加必要的命名空间，使其与 arXiv 格式兼容
    # 注意：不同版本的 feedgen 库 API 可能不同
    try:
        # 尝试使用 register_ns 方法
        fg.register_ns("dc", "http://purl.org/dc/elements/1.1/")
        fg.register_ns("content", "http://purl.org/rss/1.0/modules/content/")
    except AttributeError:
        # 如果失败，尝试使用 namespaces 属性
        try:
            fg.namespaces.update({
                'dc': 'http://purl.org/dc/elements/1.1/',
                'content': 'http://purl.org/rss/1.0/modules/content/'
            })
        except AttributeError:
            # 如果两种方法都失败，忽略命名空间注册
            logger.warning("Could not register namespaces for RSS feed, some features may not work properly.")
    
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
    
    # 添加翻译后的标题（如果有）
    if hasattr(paper, 'translated_title') and paper.translated_title:
        entry.title(f"{paper.title} / {paper.translated_title}")
    
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
    
    # 发布和更新时间
    # 使用当前时间，因为 ArxivPaper 类可能没有 published 属性
    current_time = datetime.datetime.now(datetime.timezone.utc)
    entry.published(current_time)
    entry.updated(current_time)
    
    # 分类信息
    # ArxivPaper 类可能没有 categories 属性
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
    """保存 RSS Feed 到文件，使用 Atom 格式"""
    try:
        # 确保目标目录存在
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # 使用 atom_file 而不是 rss_file，生成 Atom 格式的 feed
        feed_generator.atom_file(output_path)
        logger.info(f"RSS feed saved to {output_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to save RSS feed: {e}")
        return False
