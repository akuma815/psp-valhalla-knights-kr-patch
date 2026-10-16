"""Shared constants for the Korean character-name input pages."""

# The original hiragana and katakana layouts expose 80 and 81 kana cells plus
# one long-vowel/hyphen cell on each page.  Reuse those 81 and 82 selectable
# cells.  Use only syllables already required by the translated game so the
# name pages do not consume additional font tiles.
NAME_PAGE_ONE = (
    "아알안에엘엔오올온우울운이일인카칼케켈코콘쿠쿨가갈간게겐고골곤구굴군"
    "라랄란레로롤론루룰마말만메멜모몰몬무물문나날난네넬노놀논누눈리릴린"
    "니닌다달단데델도돌돈두둘둔바"
)

NAME_PAGE_TWO = (
    "발반베벨벤보볼본부불분사살산세셀센소솔손시실신자잘잔제젤젠조존지질진"
    "타탈탄테텐토톤티틸파팔판페펠펜포폴피필하할한헤헬호홀혼후악암애야"
    "옥옴용움유은프드릭크스퍼건서브르"
)

NAME_INPUT_CHARS = NAME_PAGE_ONE + NAME_PAGE_TWO

if len(NAME_PAGE_ONE) != 81 or len(NAME_PAGE_TWO) != 82:
    raise RuntimeError("name input pages must contain exactly 81 and 82 syllables")
if len(set(NAME_INPUT_CHARS)) != len(NAME_INPUT_CHARS):
    raise RuntimeError("name input syllables must be unique across both pages")
