import arxiv
import argparse
import os
import sys
from dotenv import load_dotenv
load_dotenv(override=True)
os.environ["TOKENIZERS_PARALLELISM"] = "false"
from pyzotero import zotero
from recommender import rerank_paper
from construct_email import render_email, send_email
from tqdm import trange,tqdm
from loguru import logger
from gitignore_parser import parse_gitignore
from tempfile import mkstemp
from paper import ArxivPaper
from llm import set_global_llm
import feedparser
from construct_rss import render_rss, save_rss

def get_zotero_corpus(id:str,key:str) -> list[dict]:
    zot = zotero.Zotero(id, 'user', key)
    collections = zot.everything(zot.collections())
    collections = {c['key']:c for c in collections}
    corpus = zot.everything(zot.items(itemType='conferencePaper || journalArticle || preprint'))
    corpus = [c for c in corpus if c['data']['abstractNote'] != '']
    def get_collection_path(col_key:str) -> str:
        if p := collections[col_key]['data']['parentCollection']:
            return get_collection_path(p) + '/' + collections[col_key]['data']['name']
        else:
            return collections[col_key]['data']['name']
    for c in corpus:
        paths = [get_collection_path(col) for col in c['data']['collections']]
        c['paths'] = paths
    return corpus

def filter_corpus(corpus:list[dict], pattern:str) -> list[dict]:
    _,filename = mkstemp()
    with open(filename,'w') as file:
        file.write(pattern)
    matcher = parse_gitignore(filename,base_dir='./')
    new_corpus = []
    for c in corpus:
        match_results = [matcher(p) for p in c['paths']]
        if not any(match_results):
            new_corpus.append(c)
    os.remove(filename)
    return new_corpus

def get_arxiv_paper(query:str, debug:bool=False) -> list[ArxivPaper]:
    from datetime import datetime, timedelta, timezone
    
    client = arxiv.Client(num_retries=10,delay_seconds=10)
    
    if not debug:
        # 确定当前日期和arXiv发布日期
        now = datetime.now(timezone.utc)
        arxiv_cutoff_hour = 20  # UTC 20:00 (晚上8点)
        
        # 如果当前时间已经过了UTC 20:00，则获取"明天"的论文
        # 否则获取"今天"的论文
        if now.hour >= arxiv_cutoff_hour:
            logger.info("当前时间已过UTC 20:00，获取下一个发布周期的论文")
            # 这里不需要特殊处理，因为RSS feed已经包含了最新的发布
        else:
            logger.info("当前时间在UTC 20:00之前，获取当前发布周期的论文")
        
        # 获取RSS feed
        feed = feedparser.parse(f"https://rss.arxiv.org/atom/{query}")
        if 'Feed error for query' in feed.feed.title:
            raise Exception(f"Invalid ARXIV_QUERY: {query}.")
        
        # 只获取标记为'new'的论文
        papers = []
        all_paper_ids = [i.id.removeprefix("oai:arXiv.org:") for i in feed.entries if i.arxiv_announce_type == 'new']
        
        if len(all_paper_ids) == 0:
            logger.info("RSS feed中没有找到标记为'new'的论文")
            return papers
            
        logger.info(f"在RSS feed中找到 {len(all_paper_ids)} 篇标记为'new'的论文")
        
        # 批量获取论文详情
        bar = tqdm(total=len(all_paper_ids), desc="Retrieving Arxiv papers")
        for i in range(0, len(all_paper_ids), 50):
            search = arxiv.Search(id_list=all_paper_ids[i:i+50])
            batch = [ArxivPaper(p) for p in client.results(search)]
            bar.update(len(batch))
            papers.extend(batch)
        bar.close()
        
        logger.info(f"成功获取 {len(papers)} 篇论文详情")

    else:
        logger.debug("Retrieve 3 arxiv papers regardless of the date.")
        search = arxiv.Search(query='cat:astro-ph.GA', sort_by=arxiv.SortCriterion.SubmittedDate)
        papers = []
        for i in client.results(search):
            papers.append(ArxivPaper(i))
            if len(papers) == 3:
                break

    return papers


parser = argparse.ArgumentParser(description='Recommender system for academic papers')

def add_argument(*args, **kwargs):
    def get_env(key:str,default=None):
        # handle environment variables generated at Workflow runtime
        # Unset environment variables are passed as '', we should treat them as None
        v = os.environ.get(key)
        if v == '' or v is None:
            return default
        return v
    parser.add_argument(*args, **kwargs)
    arg_full_name = kwargs.get('dest',args[-1][2:])
    env_name = arg_full_name.upper()
    env_value = get_env(env_name)
    if env_value is not None:
        #convert env_value to the specified type
        if kwargs.get('type') == bool:
            env_value = env_value.lower() in ['true','1']
        else:
            env_value = kwargs.get('type')(env_value)
        parser.set_defaults(**{arg_full_name:env_value})

if __name__ == '__main__':
    
    add_argument('--zotero_id', type=str, help='Zotero user ID')
    add_argument('--zotero_key', type=str, help='Zotero API key')
    add_argument('--zotero_ignore',type=str,help='Zotero collection to ignore, using gitignore-style pattern.')
    add_argument('--send_empty', type=bool, help='If get no arxiv paper, send empty email',default=False)
    add_argument('--max_paper_num', type=int, help='Maximum number of papers to recommend',default=100)
    add_argument('--arxiv_query', type=str, help='Arxiv search query')
    add_argument('--smtp_server', type=str, help='SMTP server')
    add_argument('--smtp_port', type=int, help='SMTP port')
    add_argument('--sender', type=str, help='Sender email address')
    add_argument('--receiver', type=str, help='Receiver email address')
    add_argument('--sender_password', type=str, help='Sender email password')
    add_argument(
        "--use_llm_api",
        type=bool,
        help="Use OpenAI API to generate TLDR",
        default=False,
    )
    add_argument(
        "--openai_api_key",
        type=str,
        help="OpenAI API key",
        default=None,
    )
    add_argument(
        "--openai_api_base",
        type=str,
        help="OpenAI API base URL",
        default="https://api.openai.com/v1",
    )
    add_argument(
        "--model_name",
        type=str,
        help="LLM Model Name",
        default="gpt-4o",
    )
    add_argument(
        "--language",
        type=str,
        help="Language of TLDR",
        default="English",
    )
    add_argument(
        "--generate_rss",
        type=bool,
        help="Generate RSS feed",
        default=False,
    )
    add_argument(
        "--rss_output",
        type=str,
        help="Path to save RSS feed",
        default="public/index.xml",
    )
    add_argument(
        "--rss_title",
        type=str,
        help="Title for RSS feed",
        default="ArXiv Daily Papers",
    )
    add_argument(
        "--rss_link",
        type=str,
        help="Link for RSS feed",
        default="https://arxiv.org/",
    )
    add_argument(
        "--rss_description",
        type=str,
        help="Description for RSS feed",
        default="Daily arXiv paper recommendations based on your Zotero library",
    )
    add_argument(
        "--translate_title",
        type=bool,
        help="Translate paper titles to the specified language",
        default=False,
    )
    add_argument(
        "--use_embedding_api",
        type=bool,
        help="Use embedding API instead of local sentence transformer model",
        default=False,
    )
    add_argument(
        "--embedding_api_key",
        type=str,
        help="API key for embedding API (required when use_embedding_api is True)",
        default=None,
    )
    add_argument(
        "--embedding_api_base",
        type=str,
        help="Base URL for embedding API",
        default="https://api.openai.com/v1",
    )
    add_argument(
        "--embedding_model",
        type=str,
        help="Embedding model name to use with the API",
        default="text-embedding-3-small",
    )
    add_argument(
        "--local_vectorization_model",
        type=str,
        help="Local sentence transformer model name or path (used when use_embedding_api is False)",
        default="avsolatorio/GIST-small-Embedding-v0",
    )
    parser.add_argument('--debug', action='store_true', help='Debug mode')
    args = parser.parse_args()
    assert (
        not args.use_llm_api or args.openai_api_key is not None
    )  # If use_llm_api is True, openai_api_key must be provided
    if args.debug:
        logger.remove()
        logger.add(sys.stdout, level="DEBUG")
        logger.debug("Debug mode is on.")
    else:
        logger.remove()
        logger.add(sys.stdout, level="INFO")

    logger.info("Retrieving Zotero corpus...")
    corpus = get_zotero_corpus(args.zotero_id, args.zotero_key)
    logger.info(f"Retrieved {len(corpus)} papers from Zotero.")
    if args.zotero_ignore:
        logger.info(f"Ignoring papers in:\n {args.zotero_ignore}...")
        corpus = filter_corpus(corpus, args.zotero_ignore)
        logger.info(f"Remaining {len(corpus)} papers after filtering.")
    logger.info("Retrieving Arxiv papers...")
    papers = get_arxiv_paper(args.arxiv_query, args.debug)
    if len(papers) == 0:
        logger.info("No new papers found. Yesterday maybe a holiday and no one submit their work :). If this is not the case, please check the ARXIV_QUERY.")
        if not args.send_empty:
          exit(0)
    else:
        logger.info("Reranking papers...")
        papers = rerank_paper(
            papers, 
            corpus, 
            use_embedding_api=args.use_embedding_api,
            embedding_api_key=args.embedding_api_key,
            embedding_api_base=args.embedding_api_base,
            embedding_model=args.embedding_model,
            local_vectorization_model=args.local_vectorization_model
        )
        if args.max_paper_num != -1:
            papers = papers[:args.max_paper_num]
        if args.use_llm_api:
            logger.info("Using OpenAI API as global LLM.")
            set_global_llm(api_key=args.openai_api_key, base_url=args.openai_api_base, model=args.model_name, lang=args.language)
        else:
            logger.info("Using Local LLM as global LLM.")
            set_global_llm(lang=args.language)

    html = render_email(papers)
    
    # 生成 RSS feed
    if args.generate_rss:
        logger.info("Generating RSS feed...")
        feed_url = f"{args.rss_link.rstrip('/')}/{os.path.basename(args.rss_output)}"
        feed = render_rss(
            papers, 
            feed_title=args.rss_title,
            feed_link=args.rss_link,
            feed_description=args.rss_description,
            feed_url=feed_url
        )
        if save_rss(feed, args.rss_output):
            logger.success(f"RSS feed generated successfully at {args.rss_output}")
            logger.info(f"RSS feed will be available at: {feed_url}")
        else:
            logger.error("Failed to generate RSS feed")
    
    # 发送邮件（如果失败不影响 RSS 生成）
    try:
        logger.info("Sending email...")
        send_email(args.sender, args.receiver, args.sender_password, args.smtp_server, args.smtp_port, html)
        logger.success("Email sent successfully! If you don't receive the email, please check the configuration and the junk box.")
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        logger.info("Email sending failed, but other operations completed successfully.")

