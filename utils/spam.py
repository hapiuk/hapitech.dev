# utils/spam.py — wording check for enquiries that reach us from client sites (the sites block most spam
# themselves with spamcheck.py; this is the second line). Same rules as the sites' spamcheck.looks_like_spam.
import re

LINK = re.compile(r"(https?://|www\.|\[url|<a\s|href\s*=)", re.I)
HTML = re.compile(r"<\s*/?\s*[a-z][^>]*>", re.I)
WORDS = re.compile(r"\b(casino|payid|pokies|slots?|betting|gambl\w*|crypto\w*|bitcoin|forex|viagra|cialis|porn\w*|"
                   r"escorts?|dating|loans?|seo|backlinks?|guest ?posts?|rank(?:ing)? (?:your|on) google|"
                   r"telegram|onlyfans|airdrop|nft|investment opportunit\w*)\b", re.I)
NON_LATIN = re.compile(r"[Ѐ-ӿ؀-ۿ぀-ヿ一-鿿가-힯]")


def looks_like_spam(name="", email="", message="", phone=""):
    """Returns a short reason, or None for a normal enquiry."""
    text = f"{name}\n{message}"
    links, words = len(LINK.findall(text)), {w.lower() for w in WORDS.findall(text)}
    if HTML.search(text):
        return "html"
    if LINK.search(name or ""):
        return "link in name"
    if links >= 2:
        return "links"
    if links and words:
        return "link + spam words"
    if len(words) >= 2:
        return "spam words"
    if text and len(NON_LATIN.findall(text)) > max(10, len(text) // 4):
        return "script"
    return None
