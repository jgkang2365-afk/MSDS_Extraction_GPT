import os
import base64

import sys
import re
import time
from itertools import cycle
import json
import fitz  # [蹂듦뎄 ?꾨즺] ?띿뒪??異붿텧???듭떖 ?붿쭊 遺??
import unicodedata
import requests
from opendataloader.pdf import PDFParser
import msds_utils_v3
from dotenv import load_dotenv

# .env ?뚯씪 濡쒕뱶 (?쒖뒪???섍꼍 蹂?섎낫??.env ?뚯씪 ?곗꽑 ?곸슜)
load_dotenv(override=True)

# [?꾩닔 ?명똿] API ??(?쒖뒪??蹂??異⑸룎 諛⑹?瑜??꾪빐 ?꾩슜 蹂?섎챸 ?ъ슜)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# --- V15.8.1 API 臾댄븳 ?꾩갹 濡쒖쭅 (?꾨떞 留덊겕 ?쒖뒪?? ---
api_keys_raw = [
    os.getenv("MSDS_GOOGLE_API_KEY_1"),
    os.getenv("MSDS_GOOGLE_API_KEY_2"),
    os.getenv("MSDS_GOOGLE_API_KEY_3"),
    os.getenv("MSDS_GOOGLE_API_KEY_4")
]

# ?좏슚???ㅼ뿉 蹂꾨챸(alias) 遺??valid_snipers = []
for i, key in enumerate(api_keys_raw, 1):
    if key:
        valid_snipers.append({"alias": f"?ㅻ굹?댄띁-{i}", "key": key})

if not valid_snipers:
    # ?덇굅????吏??(?섏쐞 ?명솚??
    legacy_key = os.getenv("MSDS_GOOGLE_API_KEY")
    if legacy_key:
        valid_snipers = [{"alias": "?ㅻ굹?댄띁-L", "key": legacy_key}]
    else:
        print("寃쎄퀬: ?μ쟾??援ш? API ?ㅺ? ?놁뒿?덈떎! .env瑜??뺤씤?섏꽭??")

sniper_pool = cycle(valid_snipers) if valid_snipers else None

# [V15.8.8] ?ㅻ굹?댄띁 荑⑤떎???덉??ㅽ듃由? 429瑜?諛쏆? ?ㅻ뒗 ?쇱젙 ?쒓컙 釉붾옓由ъ뒪??_sniper_cooldown = {}  # {alias: timestamp_until}
_sniper_round_robin_idx = 0

def get_next_sniper():
    """[V15.8.8] 荑⑤떎?댁씠 ?앸궃 ??以??쇱슫?쒕줈鍮덉쑝濡?諛곗젙"""
    global _sniper_round_robin_idx
    if not valid_snipers: return None
    
    now = time.time()
    n = len(valid_snipers)
    
    # 1. 荑⑤떎?댁씠 ?由???以묒뿉???쇱슫?쒕줈鍮?    for _ in range(n):
        idx = _sniper_round_robin_idx % n
        _sniper_round_robin_idx += 1
        sniper = valid_snipers[idx]
        cooldown_until = _sniper_cooldown.get(sniper["alias"], 0)
        if now >= cooldown_until:
            return sniper
    
    # 2. 紐⑤뱺 ?ㅺ? 荑⑤떎??以???媛??鍮⑤━ ?由щ뒗 ?ㅻ? ?湲???諛섑솚
    earliest_alias = min(_sniper_cooldown, key=_sniper_cooldown.get)
    wait_sec = _sniper_cooldown[earliest_alias] - now
    if wait_sec > 0:
        time.sleep(wait_sec + 0.5)
    return next(s for s in valid_snipers if s["alias"] == earliest_alias)

def mark_sniper_cooldown(sniper, cooldown_sec=60):
    """[V15.8.8] 429瑜?諛쏆? ?ㅻ굹?댄띁瑜??쇱젙 ?쒓컙 釉붾옓由ъ뒪??""
    if sniper:
        _sniper_cooldown[sniper["alias"]] = time.time() + cooldown_sec

if not OPENAI_API_KEY:
    print("寃쎄퀬: .env ?뚯씪??OPENAI_API_KEY媛 ?놁뒿?덈떎. 2李?Fallback ?붿쭊???묐룞?섏? ?딆뒿?덈떎.")

VERSION = "15.8.10"

def call_gemini_with_retry(payload, initial_sniper, max_retries=8, log_func=None):
    """[V15.8.8] 荑⑤떎???덉??ㅽ듃由??곕룞: 429 ?ㅻ뒗 60珥?釉붾옓由ъ뒪?? ?댁븘?덈뒗 ???먮룞 諛곗젙"""
    current_sniper = initial_sniper
    
    for attempt in range(max_retries):
        if not current_sniper:
            raise ValueError("?슚 ?꾨떞 ?ㅻ굹?댄띁媛 諛곗젙?섏? ?딆븯?듬땲??")
            
        api_key = current_sniper["key"]
        alias = current_sniper["alias"]
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
        
        try:
            response = requests.post(url, headers={'Content-Type': 'application/json'}, json=payload, timeout=40)
            
            if response.status_code != 200:
                error_msg = response.text
                if log_func: log_func(f"  ?뵶 {alias} ?ш꺽 ?ㅽ뙣(HTTP {response.status_code}): {error_msg[:60]}...")
                
                # [V15.8.8] 429硫??대떦 ?ㅻ? 60珥?釉붾옓由ъ뒪??                if response.status_code == 429:
                    mark_sniper_cooldown(current_sniper, cooldown_sec=60)
                elif response.status_code == 503:
                    mark_sniper_cooldown(current_sniper, cooldown_sec=30)
                
                # 荑⑤떎???덉??ㅽ듃由ш? ?뚯븘???댁븘?덈뒗 ?ㅻ? 怨⑤씪以?                current_sniper = get_next_sniper()
                if current_sniper:
                    if log_func: log_func(f"  ?봽 [{current_sniper['alias']}](??濡??먮룞 ?꾪솚")
                continue
                    
            return response.json()
            
        except requests.exceptions.RequestException as e:
            if log_func: log_func(f"  ?뵶 {alias} ?ㅽ듃?뚰겕 ?딄?: {str(e)[:60]}")
            # [V15.8.9] ?湲고븯吏 ?딄퀬 利됱떆 ?대떦 ??釉붾옓由ъ뒪????臾댁“嫄??ㅼ???            mark_sniper_cooldown(current_sniper, cooldown_sec=30)
            current_sniper = get_next_sniper()
            if current_sniper and log_func:
                log_func(f"  ?봽 [{current_sniper['alias']}](??濡??먮룞 ?꾪솚 (?듭떊 ?⑥젅 ?뚰뙆)")
            time.sleep(1) # ?꾩＜ 吏㏃? ??怨좊Ⅴ湲?            continue
            
    raise Exception(f"?슚 {max_retries}???곗냽 ?ш꺽 ?ㅽ뙣. 遺덈룄?(GPT) ?ъ엯!")

def extract_product_name_hybrid(text_chunk, image_list, current_sniper, log_func=None):
    """[V15.8.2] 議깆뇙 ?댁젣 & 怨듬?(Blank) 諛섑솚 ?⑥튂"""
    if not current_sniper or not image_list: return "", "?ㅽ뙣"

    # 1?섏씠吏 ?ъ쭊 ?곗씠??以鍮?    first_page_img = image_list[0]
    b64_data = first_page_img.get("data", "") if isinstance(first_page_img, dict) else first_page_img
    mime_type = first_page_img.get("mime_type", "image/jpeg") if isinstance(first_page_img, dict) else "image/jpeg"

    # [?듭떖] 二쇰떂??吏?쒕줈 ?ㅼ씠?댄듃???꾨＼?꾪듃
    prompt = """
    ?덈뒗 MSDS???쒗뭹紐낆쓣 ?뺥솗???뺤젙 吏볥뒗 ?꾨Ц ?먮룆愿?대떎. ?ъ쭊?먯꽌 ?ㅼ쓬 2?④퀎 ?섏튃???꾧꺽??以?섑븯??

    1. [援ъ뿭 寃⑸━]: "1. ?뷀븰?쒗뭹怨??뚯궗??愿???뺣낫" ??ぉ??李얘퀬, 洹??꾨옒遺??"2. ?좏빐?굿룹쐞?섏꽦" ??ぉ ?쒖옉 ?꾧퉴吏留??쎌뼱?? 2踰???ぉ??GHS 洹몃┝?대굹 ?덉쟾 臾멸뎄??泥좎???臾댁떆?섎씪.
    2. [?듭떖 ?寃?: '媛. ?쒗뭹紐?, '?곹뭹紐?, '?덈챸', '?쒗뭹??紐낆묶', 'Product Name' ?깆쓽 ?덉씠釉붿씠 媛由ы궎??[?쒖닔 ?쒗뭹紐?留??뺥솗??異붿텧?섎씪. 

    ?쒗뭹 踰덊샇, 移댄깉濡쒓렇 肄붾뱶, 沅뚯옣 ?⑸룄, ?쒖“???뺣낫 ??遺덊븘?뷀븳 ?띿뒪?몃뒗 ?ㅼ뒪濡??먮떒?섏뿬 ?쒓굅?섍퀬, ?ㅼ쭅 '?쒗뭹紐? 臾몄옄?대쭔 遺???ㅻ챸 ?놁씠 ????以꾨줈 異쒕젰?섎씪. 紐?李얘쿋?쇰㈃ ?꾨Т寃껊룄 異쒕젰?섏? 留덈씪.
    """

    payload = {"contents": [{"parts": [{"text": prompt}, {"inlineData": {"mimeType": mime_type, "data": b64_data}}]}]}
    try:
        # [V15.8.1] ?꾨떞 ?ㅻ굹?댄띁 ?꾩갹 ?ъ슜
        # [V15.8.5] log_func ?꾨떖 ?뚯씠???곌껐
        result = call_gemini_with_retry(payload, current_sniper, log_func=log_func)
        if result:
            pn_ai = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
            
            # AI媛 怨듬???二쇨굅???ㅽ뙣?덉쓣 ?뚮? ?鍮꾪븳 ?덉쟾留?            if pn_ai and not any(k in pn_ai for k in ["誘몄텛異?, "?뺤씤"]) and not re.search(r'[PH]\d{3}', pn_ai):
                if log_func: log_func(f" ?쒋? [?쒗뭹紐??ㅼ틪] ??鍮꾩쟾 ?ㅻ굹?댄븨 ?깃났: {pn_ai[:30]}")
                return pn_ai.replace('\n', ' ').strip(), "Vision"
    except Exception as e:
        if log_func: log_func(f" ?쒋? [?쒗뭹紐??ㅼ틪] ???ㅽ뙣: {e}")
        
    return "", "?ㅽ뙣"  # '誘몄텛異? ???源붾걫??怨듬? 諛섑솚

PATTERN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'patterns.json')

def load_v5_patterns():
    try:
        if os.path.exists(PATTERN_FILE):
            with open(PATTERN_FILE, 'r', encoding='utf-8') as f:
                return json.load(f).get("V5_PATTERNS", {})
    except Exception:
        pass
    return {}

P = load_v5_patterns()

# [V5.1 Step 3] AI ?쒖뒪???꾨＼?꾪듃 ?몃? 濡쒕뱶
def load_system_prompt():
    prompt_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'prompt_system_v5.txt')
    try:
        if not os.path.exists(prompt_path):
            raise FileNotFoundError(f"?꾨＼?꾪듃 ?뚯씪 ?꾨씫: {prompt_path}")
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except Exception as e:
        raise RuntimeError(f"[?쒖뒪??移섎챸???ㅻ쪟] AI ?꾨＼?꾪듃 濡쒕뱶 ?ㅽ뙣. prompt_system_v5.txt ?뚯씪???뺤씤?섏꽭??\n?곸꽭: {e}")

# ?꾩뿭 ?꾨＼?꾪듃 濡쒕뱶
SYSTEM_PROMPT_TEXT = load_system_prompt()

PROMPT_GEMINI_FLASH = """
?뱀떊? 1李?怨좎냽 ?쒓컖 異붿텧湲?Sniper)?낅땲?? 泥⑤???MSDS ???대?吏留?蹂닿퀬 ?곗씠?곕? 異붿텧?섏꽭??

[?뵦 1李??붿쭊 5? ?덈? ?먯튃]
1. ?슚 ?꾧꺽???섑룊(Y-axis) 1:1 留ㅼ묶: ?쒖뿉 ?좎씠 ?녾굅??移몄씠 ?볦뼱 ?깅텇紐? CAS 踰덊샇, ?⑥쑀?됱씠 ?닿툔???덈뜑?쇰룄, 諛섎뱶??媛숈? ??Row)??臾몃㎘??異붿쟻?섏뿬 1:1濡?留ㅼ묶?섎씪. ??臾쇱쭏??CAS媛 2以꾨줈 履쇨컻???덈떎硫?蹂묓빀?섎씪.
2. ?슚 ?섍컖 湲덉?(媛??以묒슂): ?쒖뿉 '?⑥쑀???대굹 '%'媛 紐낆떆??而щ읆???놁쓣 寃쎌슦, ?덈? ?놁뿉 ?덈뒗 '遺꾩옄???대굹 '?밸뒗?? 媛숈? 臾닿????レ옄瑜??⑥쑀?됱쑝濡??붽컩?쒖폒 異붿텧?섏? 留덈씪.
3. ?슚 寃곗륫移?泥섎━: CAS 移몄씠 鍮꾩뼱?덇굅??'?곸뾽鍮꾨?', '鍮꾧났媛? ?깆씠硫?媛李??놁씠 ?먭린?섎씪. 諛섎?濡?CAS???덈뒗???⑥쑀??移몄씠 鍮꾩뼱?덇굅??'-' 泥섎━?섏뼱 ?덈떎硫??⑥쑀?됱쓣 '誘멸린??'濡?異쒕젰?섎씪. ?? '?붾웾', 'balance' ?깆쑝濡?紐낆떆??寃쎌슦留?'Rem.%'濡?異쒕젰?섎씪.
4. ?슚 1% 遺?깊샇 議곗옉 湲덉?: ?먮낯??'0.1-1' ?대씪 ?곹? ?덉쑝硫?'0.1~1%'濡?異쒕젰?섎씪. ?꾩쓽濡?'<1%'泥섎읆 遺?깊샇瑜?吏?대궡???섍컖???덈? 湲덉??쒕떎.
5. ?щ㎎ ?듭씪: ?⑥쑀???レ옄 ?ㅼ뿉??諛섎뱶??'%'瑜?遺숈뿬??

JSON 異쒕젰 ?щ㎎:
{
  "援ъ꽦?깅텇": [
    {"cas_no": "123-45-6", "content": "10~20%"}
  ],
  "援먯젙_?ъ쑀": "?쒓컖 異붿텧 ?꾨즺"
}
"""

# ?슌 [2李?蹂듦뎄 ?붿썝???꾨＼?꾪듃] GPT-4o-mini ?꾩슜
PROMPT_GPT_FALLBACK = """
?뱀떊? ?뚭눼???쒕? 湲곸뼱紐⑥쑝??2李?遺덈룄?(Bulldozer)?낅땲?? 泥⑤????대?吏???쒖뿉???곗씠?곕? '?덉뿉 蹂댁씠??洹몃?濡? ?⑥닚 臾댁떇?섍쾶 蹂듭궗?섏꽭?? 

[?뵦 遺덈룄? ?⑥닚 異붿텧 4? ?먯튃]
1. ?앷컖 湲덉?: % 湲고샇 遺숈씠湲? 遺?깊샇 援먯젙, '?붾웾'??'Rem.%'濡?諛붽씀湲????대뼚??媛怨듭씠??踰덉뿭???섏? 留덉꽭?? ?꾩냽 ?붿쭊???뚯븘???⑸땲?? ?쒖뿉 ?곹엺 湲?⑤? 洹몃?濡???댄븨?섏꽭??
2. ?곸뾽鍮꾨? 諛?怨듬? ?듦낵: CAS 踰덊샇 移몄뿉 踰덊샇媛 ?녾퀬 '?곸뾽鍮꾨?', '-', '鍮꾧났媛? ?깆씠 ?곹??덈떎硫? 踰꾨━吏 留먭퀬 洹?湲?먮? 洹몃?濡?`cas_no`???곸뼱?ㅼ꽭??
3. ?ㅼ쨷 CAS ?듯빀: ??移몄뿉 CAS 踰덊샇媛 ?щ윭 媛?萸됱퀜 ?덉쑝硫??됱쓣 ?섎늻吏 留먭퀬, ?꾩뼱?곌린???щ옒??/)濡?臾띠뼱????以꾨줈 ?????ㅼ꽭??
4. ?섏씠吏 ?몃옒?? 媛??깅텇??諛쒓껄???대?吏???ㅼ젣 ?섏씠吏 踰덊샇瑜?'page' ?꾨뱶??湲곗옱?섏꽭??

JSON 異쒕젰 ?щ㎎:
{
  "援ъ꽦?깅텇": [
    {"cas_no": "123-45-6 / ?곸뾽鍮꾨?", "content": "10 誘몃쭔", "page": "3"}
  ],
  "援먯젙_?ъ쑀": "?⑥닚 臾댁떇 ?먮낯 ?띿뒪??蹂듭궗 ?꾨즺"
}
"""

# [V8.2] MES 留덉뒪???곗씠??濡쒕뱶 (Silent Failure 諛⑹뼱 諛?Fail-Safe ?곸슜)
MES_MASTER_MAP = {}
try:
    master_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'MES_MASTER_LOOKUP.json')
    
    # 1. ?뚯씪 議댁옱 ?щ? 臾쇰━???뺤씤
    if not os.path.exists(master_path):
        raise FileNotFoundError(f"留덉뒪???곗씠???뚯씪??議댁옱?섏? ?딆뒿?덈떎: {master_path}")

    with open(master_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        items_list = data.get("master_list", []) if isinstance(data, dict) and "master_list" in data else []
        
        # 2. ?곗씠???좏슚??寃利?        if not items_list:
            raise ValueError("JSON ?뚯씪 ?댁뿉 'master_list' 諛곗뿴???녾굅???곗씠?곌? 鍮꾩뼱 ?덉뒿?덈떎.")
            
        for info in items_list:
            cas_raw = str(info.get("CAS踰덊샇", "")).strip()
            # CAS 踰덊샇 ?뺢퇋??(?욎쓽 0 ?쒓굅?섏뿬 留ㅼ묶 ?뺣쪧 利앸?)
            cas = re.sub(r'^0+', '', cas_raw)
            # [?섏젙] 珥덉궛硫뷀떥 ???硫뷀떥 ?꾩꽭?뚯씠?몃? ?〓룄濡?'臾쇱쭏紐? 理쒖슦???곸슜
            std_name = info.get("臾쇱쭏紐?) or info.get("?곸슜紐?)
            if cas and std_name:
                MES_MASTER_MAP[cas] = std_name.strip()
                
except Exception as e:
    # [移섎챸??蹂寃? print濡?議곗슜???섍린吏 ?딄퀬 RuntimeError 諛쒖깮. 
    # GUI??global_exception_handler媛 罹먯튂?섏뿬 ?앹뾽?쇰줈 ?꾩슦?꾨줉 媛뺤젣??
    raise RuntimeError(f"[?쒖뒪??移섎챸???ㅻ쪟] 留덉뒪??DB 珥덇린?붿뿉 ?ㅽ뙣?덉뒿?덈떎. DB ?뚯씪???뺤씤?섏꽭??\n?곸꽭 ?먯씤: {e}")

# [V5.1 ?깅뒫 理쒖쟻?? ?뺢퇋???ъ쟾 而댄뙆??諛??꾩뿭 ?ы띁 ?⑥닔 遺꾨━
REGEX_LE = re.compile(r'(\d+(?:\.\d+)?)\s*(?:%|?꾨줈)?\s*(?:?댄븯|??<=)')
REGEX_LT = re.compile(r'(\d+(?:\.\d+)?)\s*(?:%|?꾨줈)?\s*(?:誘몃쭔|竊?<)')
REGEX_GE = re.compile(r'(\d+(?:\.\d+)?)\s*(?:%|?꾨줈)?\s*(?:?댁긽|??>=)')
REGEX_GT = re.compile(r'(\d+(?:\.\d+)?)\s*(?:%|?꾨줈)?\s*(?:珥덇낵|竊?>)')
REGEX_PM = re.compile(r'(\d+(?:\.\d+)?)\s*(?:짹|\+-)\s*(\d+(?:\.\d+)?)')

def _calc_pm_range(m):
    """?뺢퇋??留ㅼ튂 媛앹껜瑜?諛쏆븘 짹 踰붿쐞瑜?怨꾩궛?섎뒗 ?꾩뿭 ?ы띁 ?⑥닔"""
    try:
        val, pm = float(m.group(1)), float(m.group(2))
        return f"{val-pm:g}~{val+pm:g}"
    except:
        return m.group(0)

# =====================================================================
# [1?④퀎] V24 ?뺢퇋??肄붿뼱 (?덉쟾留?蹂듦뎄 ?꾨즺)
# =====================================================================
def clean_junk_from_name(name):
    if not name: return name
    name = re.split(r'\s{2,}', str(name))[0]
    junk_keywords = ["Date", "諛쒗뻾??, "媛쒖젙??, "Revision", "Rev.", "Page", "?섏씠吏", "臾쇱쭏?덉쟾蹂닿굔?먮즺", "MSDS", "?묒꽦??, "怨듦툒??, "?앸퀎??, "踰덊샇", "CAS"]
    for key in junk_keywords:
        name = re.split(rf'(?i){re.escape(key)}', name)[0]
    name = re.split(r'\d{4}[.\-/]\d{2}[.\-/]\d{2}', name)[0]
    name = re.sub(r'(.+?)\1+', r'\1', name)
    return name.strip(": ").strip()

# [V14.6] ?뺢퇋??理쒖쟻??諛??꾩뿭 ?ы띁 ?⑥닔



# [?붿쭊 ?댁옣] CAS 寃利?def verify_cas_number(cas_string):
    if not cas_string or re.search(r'[媛-?즑-zA-Z]', cas_string) or cas_string.strip() == "-": return True
    clean_cas = re.sub(r'[^0-9-]', '', cas_string)
    parts = clean_cas.split('-')
    if len(parts) != 3: return False
    try:
        check_digit = int(parts[2])
        digits = parts[0] + parts[1]
        total = sum(int(digit) * i for i, digit in enumerate(reversed(digits), 1))
        return (total % 10) == check_digit
    except: return False

def clean_number(n_str):
    try:
        f = float(n_str.replace(',', '.')) 
        if f.is_integer(): return str(int(f))
        return str(f)
    except: return n_str

def _normalize_single_content(raw):
    """[V15.8.9] 媛쒕퀎 ?⑥쑀???뺤젣 諛?臾쇰━??諛⑹뼱留?""
    v = raw.strip().replace(" ", "")
    v = re.sub(r'\([^)]*[A-Za-z媛-??[^)]*\)', '', v)
    
    # [諛⑹뼱留?1] ?뚰뙆踰?g, mg, ml ?????ы븿?섏뼱 ?덉쑝硫?遺꾩옄???섍컖?쇰줈 媛꾩＜?섍퀬 ?먭린
    if re.search(r'[a-zA-Z]', v.replace("Rem", "")):
        return "誘멸린??"

    v = re.sub(r'([0-9.]+)(?:%?)誘몃쭔(?:%?)', r'<\1', v)
    v = re.sub(r'([0-9.]+)(?:%?)?댄븯(?:%?)', r'??1', v)
    v = re.sub(r'([0-9.]+)(?:%?)珥덇낵(?:%?)', r'>\1', v)
    v = re.sub(r'([0-9.]+)(?:%?)?댁긽(?:%?)', r'??1', v)
    v = v.replace('竊?, '<').replace('竊?, '>')
    v = v.replace('<=', '??).replace('>=', '??)
    v = re.sub(r'\.0+(?=[^\d]|$)', '', v)

    # [諛⑹뼱留?2] ?묐갑??遺?깊샇 ?꾨꼍 吏??(??..???⑦꽩)
    weird_range = re.match(r'^([??]*)([0-9.]+)(?:%?)([??]*)([0-9.]+)(?:%?)$', v)
    if weird_range:
        p1, n1, p2, n2 = weird_range.groups()
        if p1 and p2: return f"{n1}~{n2}%"
        
    range_m = re.match(r'^([<>?ㅲ돟]?)([0-9.]+)[%]*[-~]([<>?ㅲ돟]?)([0-9.]+)[%]*$', v)
    if range_m:
        p1, n1, p2, n2 = range_m.groups()
        return f"{n1}~{p2}{n2}%"
        
    if "Rem" in v:
        return "Rem.%" if "%" not in v else v
        
    single_m = re.match(r'^([<>?ㅲ돟]?)([0-9.]+)%?$', v)
    if single_m:
        p, n = single_m.groups()
        return f"{p}{n}%"
        
    # ??洹쒓꺽???꾨Т寃껊룄 留욎? ?딅뒗 李뚭볼湲곕뒗 臾댁“嫄??섍컖 泥섎━
    return "誘멸린??"

def final_quality_control(components, full_text, log_func=None):
    """[V15.8.8] 吏?ν삎 ?ㅼ쨷 CAS ???⑥쑀??1:1 留ㅼ묶 遺꾨━"""
    refined = []
    has_invalid = False
    norm_text = re.sub(r'[\s\-]', '', full_text).upper() if full_text else ""
    for comp in components:
        raw_cas_field = str(comp.get("cas_no", "")).strip()

        # 1. CAS 踰덊샇遺???뱀벝??        # [V15.8.11 ?듭떖 ?섏닠] ?욌뮘濡??レ옄???섏씠?덉씠 ?곗냽???됱씤踰덊샇 瑗щ━ ?먮Ⅴ湲?諛⑹?
        cas_list = re.findall(r'(?<![\d-])(\d{1,7}-\d{2}-\d)(?![\d-])', raw_cas_field)
        # 2. 踰덊샇媛 ?꾩삁 ?녾퀬 '?곸뾽鍮꾨?'留??곹엺 寃쎌슦留?嫄곕쫫
        if not cas_list and any(w in raw_cas_field for w in ["?곸뾽鍮꾨?", "鍮꾧났媛?, "Secret"]):
            continue
        if not cas_list:
            continue

        # 3. ?⑥쑀???먮낯 異붿텧
        raw_content = str(comp.get("content", "")).strip()

        # [V15.8.8 ?듭떖] ?⑥쑀?됰룄 ?щ옒??/)濡?遺꾨━?섏뿬 CAS? 1:1 留ㅼ묶
        content_parts_raw = re.split(r'\s*/\s*', raw_content)
        content_parts = [_normalize_single_content(c) for c in content_parts_raw if c.strip()]

        # CAS 踰덊샇 ???섎굹???뺤젣 ?곗씠???앹꽦
        page_val = comp.get("page", "")
        if len(cas_list) == len(content_parts):
            for cas_raw, cv in zip(cas_list, content_parts):
                cas = re.sub(r'^0+', '', cas_raw)
                if not verify_cas_number(cas):
                    has_invalid = True
                    continue
                if cv:
                    refined.append({"cas": cas, "content": cv, "page": page_val})
        else:
            fallback_content = content_parts[0] if content_parts else ""
            for cas_raw in cas_list:
                cas = re.sub(r'^0+', '', cas_raw)
                if not verify_cas_number(cas):
                    has_invalid = True
                    continue
                if fallback_content:
                    refined.append({"cas": cas, "content": fallback_content, "page": page_val})
    try:
        check_omission(full_text, refined)
    except ValueError as e:
        if log_func: log_func(f" ?윞 [?꾨씫 媛먯?] {e}")
        has_invalid = True 
    return refined, has_invalid



# =====================================================================
# [2?④퀎] ?쒕??섏씠 AI ?숈긽釉?(???寃???붿쭊)
# =====================================================================


def find_section3_pages(doc):
    """[V15.8.3] 2踰???ぉ(鍮꾪몴以) 諛?3踰???ぉ ?뺣? ?먯?"""
    pages = []
    for i in range(len(doc)):
        text = doc[i].get_text("text")
        # 2踰??먮뒗 3踰????쒖옉 吏???먯깋
        if re.search(r'(?:SECTION\s*)?[23][\s.:]*(?:援ъ꽦|COMPOSITION)', text, re.I):
            pages.append(i)
        # 3踰??먮뒗 4踰???씠 ?섏삤硫??대떦 ?섏씠吏源뚯? ?ы븿 ???먯깋 醫낅즺
        if pages and re.search(r'(?:SECTION\s*)?[34][\s.:]*(?:?묎툒|?좏빐???꾪뿕??FIRST|HAZARDS)', text, re.I):
            if i not in pages:
                pages.append(i)
            break
    return pages

def extract_section3_images(pdf_path, current_sniper, log_func=None):
    """[V15.8.3] ???대?吏? ?④퍡 ?대떦 ?섏씠吏???띿뒪?몃쭔 援?냼 異붿텧?섏뿬 諛섑솚"""
    try:
        doc = fitz.open(pdf_path)
        pages = find_section3_pages(doc)
        
        if not pages:
            if log_func: log_func(" ?뵇 ?띿뒪??湲곕컲 ?먯? ?ㅽ뙣. ?ㅼ틪蹂??뺤같蹂?媛??..")
            recon_images = []
            for i in range(min(5, len(doc))):
                pix = doc[i].get_pixmap(matrix=fitz.Matrix(0.8, 0.8))
                recon_images.append({
                    "mimeType": "image/png", 
                    "data": base64.b64encode(pix.tobytes("png")).decode("utf-8")
                })
            
            recon_prompt = """
            ???대?吏??以?'2. 援ъ꽦?깅텇' ?먮뒗 '3. 援ъ꽦?깅텇' ?쒓? ?덈뒗 ?섏씠吏??踰덊샇(0遺???쒖옉?섎뒗 index)瑜?李얠븘??
            諛섎뱶???꾨옒 JSON ?뺤떇?쇰줈留??묐떟?섎씪: {"page_index": ?レ옄}
            李얠? 紐삵뻽?ㅻ㈃ {"page_index": -1}
            """
            recon_res = call_gemini_2_5_flash(recon_images, prompt=recon_prompt, current_sniper=current_sniper, log_func=log_func)
            
            try:
                page_idx = int(recon_res.get("page_index", -1))
            except:
                page_idx = -1
                
            if page_idx >= 0 and page_idx < len(doc):
                pages = [page_idx]
                if page_idx + 1 < len(doc):
                    pages.append(page_idx + 1)
                if log_func: log_func(f" ?렞 ?뺤같蹂묒씠 ?섏씠吏瑜?李얠븯?듬땲?? {pages}踰?諛붿씤??)
            else:
                if log_func: log_func(" ???뺤같蹂묐룄 ?쒕? 李얠? 紐삵뻽?듬땲??")
                doc.close()
                return [], "", [] # 3媛?諛섑솚?쇰줈 ?듭씪

        images = []
        raw_text = ""
        for p_idx in pages:
            page = doc[p_idx]
            raw_text += page.get_text("text") + "\n"
            pix = page.get_pixmap(matrix=fitz.Matrix(2.5, 2.5))
            b64_img = base64.b64encode(pix.tobytes("png")).decode("utf-8")
            images.append({"mimeType": "image/png", "data": b64_img})
            if len(images) >= 3: break
            
        doc.close()

        # [V15.8.4] ?뺣? ?щ씪?댁떛: 2/3踰???ぉ ?쒖옉遺??3/4踰???ぉ ?쒖옉 ?꾧퉴吏留??띿뒪??移쇱쭏
        section3_text_only = raw_text
        start_m = re.search(r'(?:SECTION\s*)?[23][\s.:]*(?:援ъ꽦|COMPOSITION)', raw_text, re.I)
        if start_m:
            end_m = re.search(r'(?:SECTION\s*)?[34][\s.:]*(?:?묎툒|?좏빐???꾪뿕??FIRST|HAZARDS)', raw_text[start_m.end():], re.I)
            if end_m:
                section3_text_only = raw_text[start_m.start():start_m.end() + end_m.start()]
            else:
                section3_text_only = raw_text[start_m.start():]

        return images, section3_text_only, pages # ?몚 ?대?吏, ?띿뒪?? ?섏씠吏 踰덊샇 紐⑸줉 諛섑솚
    except Exception:
        return [], "", []

def call_gemini_2_5_flash(image_list=None, prompt=None, current_sniper=None, log_func=None):
    """[V14.6] 1李??ㅻ굹?댄띁: 怨좎냽 ?쒓컖 異붿텧"""
    if not image_list or not current_sniper: return None
    
    final_prompt = prompt if prompt else PROMPT_GEMINI_FLASH

    # Google AI API Contents/Parts 援ъ“ 援ъ꽦
    parts = [{"text": f"{SYSTEM_PROMPT_TEXT}\n\n{final_prompt}"}]
    for img in image_list:
        parts.append({
            "inlineData": {
                "mimeType": "image/png",
                "data": img.get("data", "")
            }
        })

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "temperature": 0.0,
            "responseMimeType": "application/json"
        }
    }

    try:
        # [V15.8.5] 蹂몄쭊 濡쒓렇 ?뚯씠???곌껐!
        result = call_gemini_with_retry(payload, current_sniper, log_func=log_func)
        if result:
            candidate = result.get("candidates", [{}])[0]
            text_response = candidate.get("content", {}).get("parts", [{}])[0].get("text", "")
            return json.loads(text_response)
        return None
    except Exception as e:
        if log_func: log_func(f" ??Gemini ?몄텧 ?먮윭: {e}")
        return None

def check_omission(original_text, extracted_data):
    """
    [?덈? 諛⑹뼱 臾멸뎄: ?섏젙 湲덉? 援ъ뿭]
    以묐났 CAS 踰덊샇???섑븳 媛吏??꾨씫 ?뚮엺 ??＜瑜?留됯린 ?꾪빐 諛섎뱶??set()???ъ슜?섏뿬 怨좎쑀 媛쒖닔留?鍮꾧탳??寃?
    """
    if not original_text: return 
    
    # 1. ?먮낯 ?띿뒪?몄뿉???쒖닔 怨좎쑀 CAS留?移댁슫??(set 蹂듭썝 諛?V15.8.11 ?뺢퇋??諛⑹뼱留??곸슜)
    cas_pattern = re.compile(r'(?<![\d-])(\d{1,7}-\d{2}-\d)(?![\d-])')
    unique_cas_found = list(set(cas_pattern.findall(original_text)))
    valid_original_cas = [cas for cas in unique_cas_found if verify_cas_number(cas)]
    original_cas_count = len(valid_original_cas)
    
    # 2. 異붿텧 ?곗씠?곕룄 以묐났?쇰줈 李?뼱吏??됱쓣 媛먯븞??怨좎쑀 CAS 醫낅쪟留?移댁슫??    if isinstance(extracted_data, list):
        # [V15.8.10 ?듭떖 ?섏닠] 'cas'? 'cas_no' Key瑜?紐⑤몢 ?ъ슜?섏뿬 ?먰룺 踰꾧렇 ?닿껐
        extracted_cas_set = set([c.get("cas") or c.get("cas_no") for c in extracted_data if c.get("cas") or c.get("cas_no")])
        extracted_cas_count = len(extracted_cas_set)
    else:
        extracted_cas_set = set([c.get("cas_no") for c in extracted_data.get("援ъ꽦?깅텇", []) if c.get("cas_no")])
        extracted_cas_count = len(extracted_cas_set)
    
    if extracted_cas_count < original_cas_count:
        raise ValueError(f"?ㅻ굹?댄띁 ?꾨씫 諛쒖깮 (?먮낯:{original_cas_count} vs 異붿텧:{extracted_cas_count}). 2李?遺덈룄?(GPT) ?붿썝 ?ъ엯!")

def call_gpt_4o_mini(image_list=None, prompt=None, log_func=None):
    """[V14.6] 2李?蹂듦뎄 ?붿썝: ?ъ링 援ъ“ 遺꾩꽍"""
    if not image_list or not OPENAI_API_KEY: return None

    final_prompt = prompt if prompt else PROMPT_GPT_FALLBACK

    content_list = [{"type": "text", "text": final_prompt}]
    for img in image_list:
        content_list.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{img.get('data', '')}"}
        })

    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT_TEXT},
            {"role": "user", "content": content_list}
        ],
        "temperature": 0.0,
        "response_format": {"type": "json_object"}
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENAI_API_KEY}"
    }

    try:
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=40)
        if response.status_code == 200:
            result = response.json()
            text_response = result["choices"][0]["message"]["content"]
            return json.loads(text_response)
        else:
            if log_func: log_func(f" ?뵶 遺덈룄?(GPT) ?쒕쾭 ?먮윭: HTTP {response.status_code}")
            return None
    except Exception as e:
        if log_func: log_func(f" ?뵶 遺덈룄?(GPT) ?듭떊 ?먮윭: {str(e)[:50]}")
        return None

def process_pdf(pdf_path, log_func=None):
    start_time = time.time()
    
    current_sniper = get_next_sniper()
    alias = current_sniper["alias"] if current_sniper else "?뚯닔?놁쓬"
    
    if log_func: log_func(f" ?? [V{VERSION} Vision-Only] 遺꾩꽍 ?쒖옉 ?∽툘 ?대떦: {alias}")

    # [V15.8.3] 諛곗꽑 援먯껜: ?대?吏? 援?냼 ?띿뒪?몃? ?숈떆??諛쏆쓬 (1 PDF = 1 ?ㅻ굹?댄띁 ?먯튃)
    image_list, section3_text_for_omission, pages = extract_section3_images(pdf_path, current_sniper, log_func=log_func)
    if not image_list:
        if log_func: log_func(" ??Section 3 ?대?吏瑜?李얠쓣 ???놁뒿?덈떎.")
        return {"error": "AI 異붿텧 ?꾩쟾 ?ㅽ뙣 (?섎룞 寃???꾩슂)"}

    # 2. ?쒗뭹紐??섏씠釉뚮━???ㅼ틪 諛??꾩껜 ?띿뒪??異붿텧 (Grounding??
    full_text_for_grounding = ""
    try:
        doc = fitz.open(pdf_path)
        first_page_text = doc[0].get_text() if len(doc) > 0 else ""
        
        for page in doc:
            full_text_for_grounding += page.get_text()
            
        pix_cover = doc[0].get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
        cover_img = [{"mimeType": "image/png", "data": base64.b64encode(pix_cover.tobytes("png")).decode("utf-8")}]
        doc.close()
    except:
        cover_img = image_list 
        first_page_text = ""
        full_text_for_grounding = ""
    
    # [V15.8.7 蹂듭썝] 1 PDF = 1 ?ㅻ굹?댄띁 ?먯튃: 吏꾩엯 ??諛곗젙???ㅻ굹?댄띁瑜?怨꾩냽 ?ъ슜
    hybrid_pn, _ = extract_product_name_hybrid(first_page_text, cover_img, current_sniper, log_func=log_func)

    hybrid_pn = re.sub(r'^[\s\-_*:#=|]+', '', hybrid_pn)
    is_multi_model = False
    
    if hybrid_pn.count(',') >= 2 or len(hybrid_pn) > 60:
        is_multi_model = True

    # 3. 1李??ㅻ굹?댄띁(Flash) ?ъ엯 (吏꾩엯 ??諛곗젙???ㅻ굹?댄띁 ?ъ궗??
    if log_func: log_func(f" ?렞 1李?怨좎냽 ?ㅻ굹?댄띁({alias}) ?ъ엯")
    # [V15.8.5] ?꾨씫?섏뿀??log_func ?뚮씪誘명꽣 媛뺤젣 二쇱엯!
    ai_res = call_gemini_2_5_flash(image_list, PROMPT_GEMINI_FLASH, current_sniper=current_sniper, log_func=log_func)
    used_engine = "Gemini-Flash"

    # 4. ?ㅻ쭏??Gatekeeper (?⑹깋遺??먮퀎)
    needs_gpt = False
    valid_components = []

    if not ai_res or "援ъ꽦?깅텇" not in ai_res:
        needs_gpt = True # 援ъ“ 遺뺢눼
    else:
        for comp in ai_res.get("援ъ꽦?깅텇", []):
            cas = str(comp.get("cas_no", "")).strip()
            content_str = str(comp.get("content", "")).replace(" ", "") # 怨듬갚留??쒓굅 (理쒖냼 ?뺤젣)
            
            # [?꾪꽣留? ?곸뾽鍮꾨????ㅼ썙?쒕㈃ 1李⑥뿉?쒕룄 踰꾨┝
            if not cas or any(kw in cas for kw in ["?곸뾽鍮꾨?", "鍮꾧났媛?, "?뱀씤踰덊샇", "誘멸린??, "Secret"]):
                continue

            # [濡ㅻ갚] 1李??붿쭊(Gemini)? ?꾧꺽??湲곗? ?곸슜 (?쇳빀 ?쒓린硫??먭린?섍퀬 2李⑤줈 ?섍?)
            cas_clean = re.sub(r'^0+', '', cas) # ?욎쓽 0 ?쒓굅
            is_valid_cas = re.match(r'^\d{1,7}-\d{2}-\d$', cas_clean)
            
            if not is_valid_cas:
                needs_gpt = True # CAS 洹쒓꺽??源⑥죱?쇰㈃ 1李??붿쭊???쒓컖 ?ㅻ쪟濡?媛꾩＜, GPT ?몄텧!
                continue
                
            # [?⑹깋遺?議곌굔] ?⑥쑀???ㅻ쪟
            if not re.search(r'\d', content_str) and "Rem" not in content_str:
                needs_gpt = True 
                break
            valid_components.append(comp)
        
        # [V15.8.3] ?꾨씫 ?먯?湲? ?꾩껜 臾몄꽌媛 ?꾨땶 '?쒓? ?덈뒗 ?섏씠吏???띿뒪??留뚯쑝濡?鍮꾧탳!
        if len(valid_components) == 0:
            needs_gpt = True
        else:
            try:
                # full_text_for_grounding ???section3_text_for_omission ?ъ슜!
                check_omission(section3_text_for_omission, valid_components)
            except ValueError as e:
                if log_func: log_func(f" ?윞 {e}")
                needs_gpt = True

    # 5. 2李?蹂듦뎄 ?붿썝(GPT) ?ъ엯
    if needs_gpt:
        if log_func: log_func(" ?윞 1李??붿쭊 異붿텧 遺덇? ?먮떒. 2李??낆껜 蹂듦뎄 ?붿썝(GPT-4o-mini) ?ъ엯!")
        ai_res = call_gpt_4o_mini(image_list, PROMPT_GPT_FALLBACK)
        used_engine = "GPT-4o-mini"
        
        # GPT留덉? ?ㅽ뙣?섍굅???좏슚 ?깅텇??0媛쒕㈃ 源붾걫?섍쾶 ?ш린 (???李얠? 留?)
        if not ai_res or not ai_res.get("援ъ꽦?깅텇") or len(ai_res.get("援ъ꽦?깅텇", [])) == 0:
            if log_func: log_func(" ??紐⑤뱺 AI ?붿쭊 異붿텧 ?ㅽ뙣 (?섎룞 寃?????")
            return {
                "error": "AI 異붿텧 ?꾩쟾 ?ㅽ뙣 (?섎룞 寃???꾩슂)",
                "?쒗뭹紐?: hybrid_pn,
                "?좏샇??: "?뵶"
            }

    final_ai_result = ai_res

    # 6. ?곗씠??議곕┰ 諛?Phase 3 ?⑥닚 ?꾩쿂由?(怨듬갚 ?쒓굅)
    product_name = hybrid_pn # 1?섏씠吏?먯꽌 ?ㅻ굹?댄븨??吏꾩쭨 ?쒗뭹紐?媛뺤젣 ?곸슜

    
    # [?섏젙] AI媛 李얠? ?쒗뭹紐낆쓣 ?몄쐞?곸쑝濡??뺤젣?섏? ?딆쓬
    
    components = final_ai_result.get("援ъ꽦?깅텇", [])
    reason = final_ai_result.get("援먯젙_?ъ쑀", "?ъ쑀 ?놁쓬")
    
    # ?슚 [V15.6] 以묒븰 ?듭젣???꾪뻾 援먯젙湲?濡??곗씠???쇨큵 ?명긽
    refined_comps, has_invalid_cas = final_quality_control(components, full_text_for_grounding, log_func)
    
    comp_parts = [f"{c['cas']}({c['content']})" for c in refined_comps]

    if not comp_parts:
        if log_func: log_func(" ???좏슚???깅텇 ?곗씠?곌? 議댁옱?섏? ?딆쓬")
        return {
            "error": "AI 異붿텧 ?꾩쟾 ?ㅽ뙣 (?섎룞 寃???꾩슂)",
            "?쒗뭹紐?: hybrid_pn,
            "?좏샇??: "?뵶"
        }

    comp_str = "; ".join(comp_parts)
    target_substances = "" # ?슚 痢≪젙???蹂??異붽?

    # ----------------------------------------------------
    # ?슚 [V15.3] ?뱀젙 ?ㅼ쨷 紐⑤뜽 ?⑹젒遊?CR-13 ?쒕━利? ?섎뱶肄붾뵫 ?덉쇅 泥섎━
    if "?곌컯???쇰났?꾪겕 ?⑹젒遊? in hybrid_pn and "CS-200" in hybrid_pn and "CR-13" in hybrid_pn:
        hybrid_pn = "?⑹젒?щ즺(?곌컯???쇰났?꾪겕 ?⑹젒遊? CR-13"
        comp_str = "13463-67-7(10~15%); 68476-25-5(5~10%); 7439-96-5(1~5%); 1344-09-8(1~5%); 1317-65-3(1~5%); 12001-26-2(1~5%); 7439-89-6(Rem.%)"
        
        # ?슚 二쇰떂 吏?? 痢≪젙????띿뒪??媛뺤젣 怨좎젙!
        target_substances = "?⑹젒?? ?고솕泥?遺꾩쭊, ??; 留앷컙 諛?洹?臾닿린?뷀빀臾? ?댁궛?뷀떚???
        
        is_multi_model = True 
        if log_func: log_func(" ?좑툘 [?섎뱶肄붾뵫 ?덉쇅] CR-13 媛먯?! ?쒗뭹紐? ?깅텇, 痢≪젙???媛뺤젣 移섑솚 ?꾨즺")
    # ----------------------------------------------------

    # ?슚 [V15.2 ?듭떖] AI 異붿텧? 臾댁궗???앸궗?쇰굹, ?ㅼ쨷 紐⑤뜽?대?濡??윞?⑹깋遺덈줈 媛뺤젣 蹂寃?
    if is_multi_model:
        return {
            "援ъ꽦?깅텇": comp_str,
            "?쒗뭹紐?: hybrid_pn,
            "痢≪젙???: target_substances, # ?몚 媛뺤젣 ?쎌엯!
            "援먯젙_?ъ쑀": "?ㅼ쨷 紐⑤뜽(?쒕━利? 臾몄꽌 媛먯? ?먮뒗 ?쒖? ?덉쇅 移섑솚",
            "?좏샇??: "?윞",
            "used_engine": "flash" if used_engine == "Gemini-Flash" else "bulldozer" # ?몚 GUI 洹쒓꺽??留욊쾶 蹂?섑븯??異붽?!
        }

    # ?뺤긽 ?⑥씪 紐⑤뜽??寃쎌슦
    tag = f"[{used_engine}-PASS]"
    gui_engine_name = "flash" if used_engine == "Gemini-Flash" else "bulldozer" # ?몚 怨듯넻 蹂??異붽?
    
    # [V15.8.2 ?⑥튂] ?쒗뭹紐낆씠 怨듬?('')??寃쎌슦 ?섎룞 ?뺤씤???꾪빐 ?⑹깋遺??윞) 諛섑솚
    if not hybrid_pn:
        return {
            "援ъ꽦?깅텇": comp_str,
            "?쒗뭹紐?: "",
            "痢≪젙???: target_substances,
            "援먯젙_?ъ쑀": "?쒗뭹紐?異붿텧 ?ㅽ뙣 - ?섎룞 ?뺤씤 ?붾쭩",
            "?좏샇??: "?윞",
            "used_engine": gui_engine_name
        }

    # [V15.5 異붽?] 媛吏?CAS媛 ?먯???寃쎌슦 珥덈줉遺??윟) 李⑤떒 諛??⑹깋遺??윞) 媛뺤젣 ?꾪솚
    final_signal = "?윟"
    final_reason = reason
    if has_invalid_cas:
        final_signal = "?윞"
        final_reason = f"{reason} (?좑툘 ?쇰? 遺?곸젅??CAS ?щ㎎ 媛먯? 諛??쒖쇅??"

    return {
        "援ъ꽦?깅텇": comp_str,
        "?쒗뭹紐?: hybrid_pn,
        "痢≪젙???: target_substances,
        "援먯젙_?ъ쑀": final_reason,
        "?좏샇??: final_signal,
        "used_engine": gui_engine_name # ?몚 異붽?!
    }

# [V7.0] GUI ?명솚?깆쓣 ?꾪븳 蹂꾩묶 ?ㅼ젙
analyze_msds = process_pdf

# =====================================================================
# [V15.8.9] ?붿쭊 ?먭? 寃利?(Regression Defense Block)
# =====================================================================
def self_test_regression():
    """紐⑤뱢 濡쒕뱶 ??怨쇨굅???곗죱???ｌ? 耳?댁뒪?ㅼ쓣 ?ъ쟾 寃利앺븯??肄붿뼱 ?ㅼ뿼???먯쿇 李⑤떒?⑸땲??"""
    # 1. ?섍컖 ?꾪꽣 ?뚯뒪??    assert _normalize_single_content("??5%??00%") == "95~100%", "?뚭? ?ㅻ쪟: ?묐갑??遺?깊샇 ?뚭눼??
    assert _normalize_single_content("77.08g") == "誘멸린??", "?뚭? ?ㅻ쪟: ?⑥쐞(g) ?섍컖 ?꾪꽣 ?뚭눼??
    assert _normalize_single_content("10-20") == "10~20%", "?뚭? ?ㅻ쪟: 湲곕낯 踰붿쐞 ?뺢퇋???뚭눼??
    
    # 2. ?ㅼ쨷 CAS ?명룷 遺꾩뿴 濡쒖쭅(V15.8.7 ?깃났 耳?댁뒪) 蹂댁〈 ?뚯뒪??    dummy_comps = [{"cas_no": "92128-87-5 / 308068-11-3", "content": "1%"}]
    res, _ = final_quality_control(dummy_comps, "")
    assert len(res) == 2, "?뚭? ?ㅻ쪟: ?ㅼ쨷 CAS 遺꾨━(?명룷 遺꾩뿴) 濡쒖쭅 ?뚭눼??
    assert res[0]["cas"] == "92128-87-5", "?뚭? ?ㅻ쪟: CAS ?뺤젣 ?뚭눼??
    
    # 3. ?곸뾽鍮꾨? ?꾧뎔 ?ш꺽 李⑤떒(V15.8.7 ?깃났 耳?댁뒪) 蹂댁〈 ?뚯뒪??    dummy_comps2 = [{"cas_no": "64-17-5 (?곸뾽鍮꾨?)", "content": "10%"}]
    res2, _ = final_quality_control(dummy_comps2, "")
    assert len(res2) == 1, "?뚭? ?ㅻ쪟: ?곸뾽鍮꾨? 蹂댁〈 濡쒖쭅 ?뚭눼??
    
    print("[OK] ?붿쭊 ?먭? 寃利?Unit Test) ?듦낵: ?뚭? ?ㅻ쪟 ?놁쓬.")

# ?뚯씪 濡쒕뱶 ???먮룞 ?ㅽ뻾
self_test_regression()
