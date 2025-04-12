from paper import ArxivPaper
from feedgen.feed import FeedGenerator
import datetime
import os
from loguru import logger
import re
from lxml import etree

def sanitize_html(html_content):
    """移除不适合在 RSS 中使用的 HTML 标签和属性"""
    # 移除 style 属性
    html_content = re.sub(r'style="[^"]*"', '', html_content)
    # 移除 class 属性
    html_content = re.sub(r'class="[^"]*"', '', html_content)
    # 移除表格标签但保留内容
    html_content = re.sub(r'<table[^>]*>', '<div>', html_content)
    html_content = re.sub(r'</table>', '</div>', html_content)
    html_content = re.sub(r'<tr[^>]*>', '<div>', html_content)
    html_content = re.sub(r'</tr>', '</div>', html_content)
    html_content = re.sub(r'<td[^>]*>', '<div>', html_content)
    html_content = re.sub(r'</td>', '</div>', html_content)
    
    return html_content

def get_paper_html(paper: ArxivPaper):
    """为单篇论文生成 HTML 内容，适合 RSS Feed 使用"""
    title = paper.title
    if paper.translated_title:
        title += f"<br>{paper.translated_title}"
    
    authors = [a.name for a in paper.authors[:5]]
    authors_text = ', '.join(authors)
    if len(paper.authors) > 5:
        authors_text += ', ...'
    
    if paper.affiliations is not None:
        affiliations = paper.affiliations[:5]
        affiliations_text = ', '.join(affiliations)
        if len(paper.affiliations) > 5:
            affiliations_text += ', ...'
    else:
        affiliations_text = 'Unknown Affiliation'
    
    html = f"""
    <div>
        <h2>{title}</h2>
        <p><strong>Authors:</strong> {authors_text}</p>
        <p><i>{affiliations_text}</i></p>
        <p><strong>arXiv ID:</strong> {paper.arxiv_id}</p>
        <p><strong>TLDR:</strong> {paper.tldr}</p>
        <p>
            <a href="{paper.pdf_url}">PDF</a>
            {f'<a href="{paper.code_url}">Code</a>' if paper.code_url else ''}
        </p>
    </div>
    """
    
    return sanitize_html(html)

def render_rss(papers: list[ArxivPaper], feed_title: str = "Daily arXiv Papers", feed_link: str = None, feed_description: str = "Daily arXiv paper recommendations"):
    """生成 RSS Feed，格式类似于 arXiv 官方的 Atom feed"""
    # 使用 Atom 格式，这与 arXiv 官方使用的格式相同
    fg = FeedGenerator()
    fg.id(feed_link if feed_link else "https://github.com/Mynanase/zotero-arxiv-daily")
    fg.title(feed_title)
    fg.link(href=feed_link if feed_link else "https://github.com/Mynanase/zotero-arxiv-daily", rel='alternate')
    # 添加 self 链接，这对 RSS 阅读器很重要
    if feed_link:
        fg.link(href=f"{feed_link}/feed.xml", rel='self')
    else:
        fg.link(href="https://github.com/Mynanase/zotero-arxiv-daily/feed.xml", rel='self')
    fg.subtitle(feed_description)  # 使用 subtitle 而不是 description，与 Atom 格式一致
    fg.language('en')
    
    # 添加时区信息以避免 ValueError: Datetime object has no timezone info
    today = datetime.datetime.now(datetime.timezone.utc)
    fg.updated(today)  # 在 Atom 中使用 updated 而不是 pubDate
    
    if not papers:
        # 如果没有论文，添加一个空条目
        fe = fg.add_entry()
        fe.id(f"no-papers-{today.strftime('%Y-%m-%d')}")
        fe.title("No Papers Today")
        fe.summary("No new papers found today. Take a rest!")  # 使用 summary 而不是 description
        fe.updated(today)  # 使用 updated 而不是 pubDate
        fe.link(href="https://github.com/Mynanase/zotero-arxiv-daily")
    else:
        # 为每篇论文添加一个条目
        for paper in papers:
            fe = fg.add_entry()
            # 使用 arXiv ID 作为唯一标识符
            arxiv_url = f"https://arxiv.org/abs/{paper.arxiv_id}"
            fe.id(arxiv_url)
            
            # 标题（包括翻译的标题，如果有）
            title = paper.title
            if paper.translated_title:
                title = f"{title} | {paper.translated_title}"
            fe.title(title)
            
            # 添加作者信息，每个作者单独添加
            for author in paper.authors[:10]:  # 限制作者数量
                fe.author(name=author.name)
            
            # 使用 summary 代替 description
            fe.summary(paper.tldr if paper.tldr else paper.summary)
            
            # 更新时间
            fe.updated(today)
            
            # 添加主链接（指向 arXiv 页面）
            fe.link(href=arxiv_url)
            
            # 添加 PDF 链接，使用特殊的 rel 和 type 属性，帮助 Zotero 识别
            fe.link(href=paper.pdf_url, rel='alternate', type='application/pdf')
            
            # 如果有代码链接，也添加
            if paper.code_url:
                fe.link(href=paper.code_url, rel='related', title='Code')
    
    return fg

def save_rss(feed_generator, output_path: str = "feed.xml"):
    """保存 RSS Feed 到文件，使用 Atom 格式"""
    try:
        # 使用 atom_file 而不是 rss_file，生成 Atom 格式的 feed
        feed_generator.atom_file(output_path)
        
        # 添加额外的处理，确保 Zotero 兼容性
        # 读取生成的文件并进行后处理
        tree = etree.parse(output_path)
        root = tree.getroot()
        
        # 添加 Zotero 可能需要的命名空间
        root.set('{http://www.w3.org/2000/xmlns/}dc', 'http://purl.org/dc/elements/1.1/')
        root.set('{http://www.w3.org/2000/xmlns/}content', 'http://purl.org/rss/1.0/modules/content/')
        
        # 保存修改后的文件
        tree.write(output_path, xml_declaration=True, encoding='UTF-8')
        
        logger.success(f"Atom feed saved to {output_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to save Atom feed: {e}")
        return False
