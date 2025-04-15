import math

def get_star_rating(score: float) -> str:
    """将相关度分数转换为星级评分字符串
    
    Args:
        score: 相关度分数
        
    Returns:
        str: 星级评分字符串，如 "⭐⭐⭐"
    """
    low = 6  # 最低分数阈值
    high = 8  # 最高分数阈值
    
    if score <= low:
        return ""
    elif score >= high:
        return "⭐⭐⭐⭐⭐"  # 5颗星
    else:
        # 将分数范围映射到1-5颗星
        normalized_score = (score - low) / (high - low)  # 0 到 1 之间
        star_count = max(1, min(5, round(normalized_score * 5)))  # 1 到 5 之间
        return "⭐" * star_count
