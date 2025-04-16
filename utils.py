import math

def get_star_rating(score: float) -> int:
    """将相关度分数转换为星级评分数量
    
    Args:
        score: 相关度分数
        
    Returns:
        int: 星级数量，0-5之间的整数，0表示不显示星级
    """
    mean = 4.5
    half = 1
    low = mean - half  # 最低分数阈值
    high = mean + half  # 最高分数阈值
    
    if score <= low:
        return 0  # 不显示星级
    elif score >= high:
        return 5  # 5颗星
    else:
        # 将分数范围映射到1-5颗星
        normalized_score = (score - low) / (high - low)  # 0 到 1 之间
        return max(1, min(5, round(normalized_score * 5)))  # 1 到 5 之间
