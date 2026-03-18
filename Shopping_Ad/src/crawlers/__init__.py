from .skstoa import SKStoaCrawler
from .lotte import LotteCrawler
from .gongyoung import GongyoungCrawler
from .kt_alpha import KTAlphaCrawler
from .cj_onstyle import CJOnstyleCrawler
from .lg_hellovision import LGHellovisionCrawler

ALL_CRAWLERS = [
    SKStoaCrawler,
    LotteCrawler,
    GongyoungCrawler,
    KTAlphaCrawler,
    CJOnstyleCrawler,
    LGHellovisionCrawler,
]

__all__ = [
    "SKStoaCrawler",
    "LotteCrawler",
    "GongyoungCrawler",
    "KTAlphaCrawler",
    "CJOnstyleCrawler",
    "LGHellovisionCrawler",
    "ALL_CRAWLERS",
]
