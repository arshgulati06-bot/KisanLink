"""
KisanLink assistant — answers from the application's own data.
================================================================

No LLM is configured for this project, and inventing one would mean either
shipping a credential we do not have or faking replies. Instead this answers a
bounded set of the questions farmers actually ask, using the SAME data the
dashboard shows: the loaded mandi archive, the crop-quality models, the
farmer's own lots and offers.

Design rules:
  - every figure comes from the real pipeline; nothing is invented
  - when the data needed for an answer is missing, it says so plainly
  - it never claims to be a general-purpose AI

Language handling:
  Questions arrive in English, Devanagari Hindi, or Roman Hindi ("Hinglish"),
  often mixed: "bhai mere tamatar ka kya bhaav hai". Intent detection works on
  a normalised form and matches keyword sets from all three, so transliteration
  is not required. Replies are rendered in the caller's selected language.
"""

from __future__ import annotations

import re
import unicodedata

#: Languages with hand-written reply templates. Any other locale falls back to
#: English rather than machine-translating into something unidiomatic.
SUPPORTED_REPLY_LANGS = ("en", "hi")

#: intent -> keyword sets. English, Devanagari and Roman-Hindi spellings sit in
#: one list per intent, so a mixed sentence matches without transliteration.
INTENT_KEYWORDS = {
    "price": [
        "price", "rate", "bhav", "bhaav", "daam", "dam", "kimat", "keemat",
        "भाव", "दाम", "कीमत", "रेट", "mandi rate", "market price",
    ],
    "best_market": [
        "best market", "best mandi", "kaunsi mandi", "konsi mandi", "kaha bechu",
        "kahan bechu", "kaha bechna", "kahan bechna", "where should i sell",
        "which market", "which mandi", "कौन", "कहाँ बेच", "कहां बेच", "मंडी",
        "sabse acchi mandi", "best net",
    ],
    "sell_or_wait": [
        "sell now", "should i sell", "abhi bechu", "abhi bech", "kab bechu",
        "kab bech", "wait karu", "ruk jau", "ruku", "hold karu",
        "बेचूं", "बेचना चाहिए", "कब बेच", "इंतजार", "रुक",
    ],
    "forecast": [
        "forecast", "outlook", "prediction", "predict", "next week", "7 day",
        "seven day", "future", "aage ka", "agle hafte", "bhavishya",
        "पूर्वानुमान", "अनुमान", "आगे", "अगले",
    ],
    "quality": [
        "quality", "grade", "condition", "kaisa hai", "kaisi hai", "gunvatta",
        "guality", "फसल कैसी", "गुणवत्ता", "ग्रेड", "क्वालिटी",
    ],
    "buyers": [
        "buyer", "buyers", "kharidar", "khareedar", "grahak", "offer", "offers",
        "खरीदार", "ग्राहक", "प्रस्ताव", "who will buy", "demand",
    ],
    "lots": [
        "my lot", "my lots", "sale lot", "meri lot", "mere lot", "listing",
        "मेरी लॉट", "मेरे लॉट", "सूची",
    ],
    "weather": [
        "weather", "rain", "mausam", "barish", "baarish",
        "मौसम", "बारिश", "बरसात",
    ],
    "help": ["help", "madad", "kya kar sakte", "मदद", "क्या कर सकते", "what can you do"],
}

#: Crop names a farmer types, mapped to the dataset's own commodity spelling.
CROP_ALIASES = {
    "tomato": "Tomato", "tamatar": "Tomato", "टमाटर": "Tomato",
    "onion": "Onion", "pyaz": "Onion", "pyaaz": "Onion", "प्याज": "Onion",
    "potato": "Potato", "aloo": "Potato", "alu": "Potato", "आलू": "Potato",
    "wheat": "Wheat", "gehu": "Wheat", "gehun": "Wheat", "गेहूं": "Wheat",
    "rice": "Rice", "chawal": "Rice", "चावल": "Rice",
    "banana": "Banana", "kela": "Banana", "केला": "Banana",
    "chilli": "Green Chilli", "mirchi": "Green Chilli", "मिर्च": "Green Chilli",
    "cotton": "Cotton", "kapas": "Cotton", "कपास": "Cotton",
    "soyabean": "Soyabean", "soybean": "Soyabean", "सोयाबीन": "Soyabean",
    "maize": "Maize", "makka": "Maize", "मक्का": "Maize",
    "sugarcane": "Sugarcane", "ganna": "Sugarcane", "गन्ना": "Sugarcane",
}


def _normalise(text: str) -> str:
    """Lowercase, strip accents/punctuation, collapse spaces — for matching only."""
    text = unicodedata.normalize("NFKC", str(text or "")).lower()
    text = re.sub(r"[^\wऀ-ॿ\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def detect_language(text: str) -> str:
    """
    'hi' for Devanagari or clearly Roman-Hindi input, else 'en'.

    Used only when the caller did not state a language; an explicit selection
    always wins.
    """
    if re.search(r"[ऀ-ॿ]", str(text or "")):
        return "hi"
    words = set(_normalise(text).split())
    romanised = {
        "bhai", "mera", "meri", "mere", "kya", "kyaa", "hai", "kaisa", "kaisi",
        "kaha", "kahan", "kaun", "kaunsi", "konsi", "bechu", "bechna", "abhi",
        "kab", "chahiye", "batao", "bata", "mujhe", "karu", "ruk", "acha",
        "accha", "thik", "theek", "bhav", "bhaav", "daam", "mandi", "fasal",
    }
    return "hi" if len(words & romanised) >= 2 else "en"


def detect_intent(text: str) -> str:
    """Best-matching intent, or 'unknown'. Longer keywords win over shorter."""
    norm = _normalise(text)
    best, best_len = "unknown", 0
    for intent, keys in INTENT_KEYWORDS.items():
        for key in keys:
            k = _normalise(key)
            if k and k in norm and len(k) > best_len:
                best, best_len = intent, len(k)
    return best


def detect_crop(text: str):
    """The commodity mentioned, in the dataset's own spelling, or None."""
    norm = _normalise(text)
    for alias, canonical in CROP_ALIASES.items():
        a = _normalise(alias)
        if a and re.search(r"\b" + re.escape(a) + r"\b", norm):
            return canonical
    return None


# =============================================================================
# Reply templates
# =============================================================================
#
# Written by hand for English and Hindi. Every {placeholder} is filled from a
# real query against the loaded data — never from a constant.

REPLIES = {
    "price": {
        "en": ("{crop} last traded at ₹{price:,.0f}/quintal at {market}, "
               "{district} on {date}. {freshness}"),
        "hi": ("{crop} का अंतिम दर्ज भाव {market}, {district} में {date} को "
               "₹{price:,.0f}/क्विंटल था। {freshness}"),
    },
    "price_none": {
        "en": ("I could not find any mandi records for {crop} in the loaded "
               "archive. Try another crop, or check the Market Prices section."),
        "hi": ("लोड किए गए आंकड़ों में {crop} का कोई मंडी रिकॉर्ड नहीं मिला। "
               "दूसरी फसल आज़माएँ या Market Prices अनुभाग देखें।"),
    },
    "no_crop": {
        "en": "Which crop do you mean? For example: \"tomato ka bhav kya hai\".",
        "hi": "आप किस फसल की बात कर रहे हैं? जैसे: \"टमाटर का भाव क्या है\"।",
    },
    "quality": {
        "en": ("Your last photo check on {crop} came back as {grade} — "
               "condition {condition}, model confidence {confidence:.0f}%.{caveat}"),
        "hi": ("आपकी पिछली {crop} फ़ोटो जाँच में {grade} मिला — "
               "स्थिति {condition}, मॉडल विश्वास {confidence:.0f}%।{caveat}"),
    },
    "quality_none": {
        "en": ("You have not run a photo quality check yet. Open Crop Quality, "
               "choose the crop and upload a photo — it is trained for "
               "{crops}."),
        "hi": ("आपने अभी तक फ़ोटो गुणवत्ता जाँच नहीं की है। Crop Quality खोलें, "
               "फसल चुनें और फ़ोटो अपलोड करें — यह {crops} के लिए प्रशिक्षित है।"),
    },
    "lots": {
        "en": "You have {n} sale lot(s) listed. Most recent: {detail}.",
        "hi": "आपकी {n} बिक्री लॉट सूचीबद्ध हैं। सबसे नई: {detail}।",
    },
    "lots_none": {
        "en": ("You have no sale lots yet. Use Create Sale Lot, or run Sell Now "
               "to prefill one from the best-market comparison."),
        "hi": ("अभी आपकी कोई बिक्री लॉट नहीं है। Create Sale Lot इस्तेमाल करें, "
               "या Sell Now चलाकर सर्वोत्तम मंडी से भरी हुई लॉट बनाएँ।"),
    },
    "buyers": {
        "en": "You have {n} offer(s). Most recent: {detail}.",
        "hi": "आपके पास {n} प्रस्ताव हैं। सबसे नया: {detail}।",
    },
    "buyers_none": {
        "en": ("No buyer offers yet. Publish a sale lot so buyers can see it — "
               "offers then appear under Received Offers."),
        "hi": ("अभी कोई खरीदार प्रस्ताव नहीं है। एक बिक्री लॉट प्रकाशित करें ताकि "
               "खरीदार उसे देख सकें — प्रस्ताव Received Offers में दिखेंगे।"),
    },
    "best_market": {
        "en": ("Open Best Market, set your location and quantity, then press "
               "Find Best Net Market. It ranks mandis by what you actually keep "
               "after transport, handling and mandi fees — not by headline price."),
        "hi": ("Best Market खोलें, अपना स्थान और मात्रा भरें, फिर Find Best Net "
               "Market दबाएँ। यह मंडियों को उस राशि से क्रमबद्ध करता है जो परिवहन, "
               "हैंडलिंग और मंडी शुल्क के बाद आपके पास बचती है।"),
    },
    "sell_or_wait": {
        "en": ("Run Sell Now for your crop and district. It compares the latest "
               "available price against the 7-day Chronos forecast and the cost "
               "of reaching each mandi, then recommends selling or waiting."),
        "hi": ("अपनी फसल और ज़िले के लिए Sell Now चलाएँ। यह नवीनतम उपलब्ध भाव की "
               "तुलना 7-दिन के Chronos पूर्वानुमान और हर मंडी तक पहुँचने की लागत से "
               "करता है, फिर बेचने या रुकने की सलाह देता है।"),
    },
    "forecast": {
        "en": ("Use Price Outlook: choose crop, state, district and market, then "
               "Generate Forecast. Chronos returns 7 days of P10/P50/P90 from "
               "that market's own history. Those are model outputs, not live "
               "mandi quotes."),
        "hi": ("Price Outlook का उपयोग करें: फसल, राज्य, ज़िला और मंडी चुनकर "
               "Generate Forecast दबाएँ। Chronos उसी मंडी के इतिहास से 7 दिन का "
               "P10/P50/P90 देता है। ये मॉडल के अनुमान हैं, लाइव मंडी भाव नहीं।"),
    },
    "weather": {
        "en": ("The weather strip at the top of the dashboard shows the current "
               "reading, humidity, rain chance and wind for your district, from "
               "Open-Meteo. If it says unavailable, press Retry."),
        "hi": ("डैशबोर्ड के ऊपर मौसम पट्टी आपके ज़िले का वर्तमान तापमान, नमी, बारिश "
               "की संभावना और हवा दिखाती है (स्रोत: Open-Meteo)। अनुपलब्ध दिखे तो "
               "Retry दबाएँ।"),
    },
    "help": {
        "en": ("I answer from KisanLink's own data. Ask me about mandi prices, "
               "your crop quality grade, the 7-day forecast, the best market to "
               "sell in, your sale lots or buyer offers — in English, Hindi or "
               "Hinglish."),
        "hi": ("मैं KisanLink के अपने आंकड़ों से उत्तर देता हूँ। मुझसे मंडी भाव, "
               "आपकी फसल की गुणवत्ता, 7-दिन का पूर्वानुमान, सर्वोत्तम मंडी, आपकी "
               "बिक्री लॉट या खरीदार प्रस्तावों के बारे में पूछें — अंग्रेज़ी, हिंदी "
               "या हिंग्लिश में।"),
    },
    "unknown": {
        "en": ("I did not understand that one. I can help with mandi prices, "
               "crop quality, the 7-day forecast, the best market, your sale "
               "lots and buyer offers. Try: \"tomato ka bhav kya hai\"."),
        "hi": ("यह समझ नहीं आया। मैं मंडी भाव, फसल गुणवत्ता, 7-दिन का पूर्वानुमान, "
               "सर्वोत्तम मंडी, आपकी बिक्री लॉट और खरीदार प्रस्तावों में मदद कर सकता "
               "हूँ। आज़माएँ: \"टमाटर का भाव क्या है\"।"),
    },
}

FRESHNESS = {
    "en": {
        "live": "This is today's official reading.",
        "old": "This is the latest available record, {days} day(s) old — not a live quote.",
    },
    "hi": {
        "live": "यह आज का आधिकारिक आंकड़ा है।",
        "old": "यह नवीनतम उपलब्ध रिकॉर्ड है, {days} दिन पुराना — लाइव भाव नहीं।",
    },
}


def reply_for(key: str, lang: str, **kw) -> str:
    """Render a template in `lang`, falling back to English for other locales."""
    lang = lang if lang in SUPPORTED_REPLY_LANGS else "en"
    template = REPLIES.get(key, REPLIES["unknown"])
    return template.get(lang, template["en"]).format(**kw)
