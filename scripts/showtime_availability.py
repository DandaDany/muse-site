"""Observed source availability for the multi-day crawl.

Values are inclusive day offsets from the Taiwan crawl date.  They are crawl
ceilings, not UI settings: the frontend only renders dates actually exported
in ``available_dates``.  The observations and evidence live in
``docs/P0_A_MULTI_DAY_RESEARCH.md``.
"""

from __future__ import annotations


SOURCE_LOOKAHEAD_DAYS: dict[str, int] = {
    # Each value is the farthest contiguous date observed during the spike.
    # Sources with sparse presales beyond that window remain a documented risk.
    "威秀影城 / VIESHOW + MUVIE CINEMAS": 8,
    "秀泰影城": 10,
    "國賓影城": 8,
    "新光影城": 0,
    "in89 豪華影城": 4,
    "喜樂時代影城": 0,
    "美麗新影城": 0,
    "天台影城": 4,
    "哈拉影城": 0,
    "美麗華影城": 6,
    "南台影城": 0,
    "樂聲影城": 1,
    "台鋁影城": 4,
    "鴻金寶麻吉影城": 1,
    "光點華山電影館": 0,
    "微風影城": 8,
    "總督數位影城": 8,
    "誠品電影院": 0,
    "南投戲院": 1,
    "埔里山明影城": 0,
    "清水時代影城": 0,
    "威尼斯影城": 0,
    "親親影城 / 親親戲院": 1,
    "王牌映画影城": 0,
    "環球中華影城": 2,
    "百老匯影城": 0,
    "高雄環球影城": 0,
    "中影屏東影城": 0,
    "新月豪華影城": 4,
    "日新戲院 / 宜蘭電影資訊網": 0,
    "金獅影城": 0,
}

MAX_SOURCE_LOOKAHEAD_DAYS = max(SOURCE_LOOKAHEAD_DAYS.values())


def source_supports_offset(source_name: str, day_offset: int) -> bool:
    return 0 <= day_offset <= SOURCE_LOOKAHEAD_DAYS.get(source_name, 0)
