import re


def _clean_text_for_match(text: str) -> str:
    if not text:
        return ""
    # Remove emojis and zero-width characters (using a broad unicode range for emojis and symbols)
    text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
    text = re.sub(r'[\u2600-\u27bf]', '', text)
    text = re.sub(r'[\u2B50]', '', text)  # ⭐
    # Remove all whitespace and zero width joiners to make fuzzy match extremely forgiving
    text = re.sub(r'[\s\u200b\u200e\u200f\u202a-\u202e]', '', text)
    # Remove all common punctuation
    text = re.sub(r'[!"#$%&\'()*+,-./:;<=>?@\[\]^_`{|}~，。！？；：“”‘’（）【】《》]', '', text)
    return text.strip().lower()

target1 = "签到"
btn1 = "🤖 签到"
print(f"Test 1: '{target1}' inside '{btn1}' -> {_clean_text_for_match(target1)} in {_clean_text_for_match(btn1)}")

target2 = "Check-in"
btn2 = "✅ Check-in"
print(f"Test 2: '{target2}' inside '{btn2}' -> {_clean_text_for_match(target2)} in {_clean_text_for_match(btn2)}")

# Let's see what \punctuation is doing, because Python's re.sub won't recognize \punctuation unless it's a specific flag or string constant
target3 = "Check-in"
print(f"Test 3 Check-in: {_clean_text_for_match(target3)}")
