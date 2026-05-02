import os
import base64
import sys
import re
import time
from itertools import cycle
import json
import fitz 
import unicodedata
import requests
from opendataloader.pdf import PDFParser
import msds_utils_v3
from dotenv import load_dotenv

# .env ?뚯씪 濡쒕뱶
load_dotenv(override=True)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

api_keys_raw = [
    os.getenv("MSDS_GOOGLE_API_KEY_1"),
    os.getenv("MSDS_GOOGLE_API_KEY_2"),
    os.getenv("MSDS_GOOGLE_API_KEY_3"),
    os.getenv("MSDS_GOOGLE_API_KEY_4")
]

valid_snipers = []
for i, key in enumerate(api_keys_raw, 1):
    if key:
        valid_snipers.append({"alias": f"?ㅻ굹?댄띁-{i}", "key": key})

if not valid_snipers:
    legacy_key = os.getenv("MSDS_GOOGLE_API_KEY")
    if legacy_key:
        valid_snipers = [{"alias": "?ㅻ굹?댄띁-L", "key": legacy_key}]
    else:
        print("寃쎄퀬: ?μ쟾??援ш? API ?ㅺ? ?놁뒿?덈떎! .env瑜??뺤씤?섏꽭??")

sniper_pool = cycle(valid_snipers) if valid_snipers else None
_sniper_cooldown = {} 
_sniper_round_robin_idx = 0

def get_next_sniper():
    global _sniper_round_robin_idx
    if not valid_snipers: return None
    now = time.time()
    n = len(valid_snipers)
    for _ in range(n):
        idx = _sniper_round_robin_idx % n
        _sniper_round_robin_idx += 1
        sniper = valid_snipers[idx]
        cooldown_until = _sniper_cooldown.get(sniper["alias"], 0)
        if now >= cooldown_until:
            return sniper
    earliest_alias = min(_sniper_cooldown, key=_sniper_cooldown.get)
    wait_sec = _sniper_cooldown[earliest_alias] - now
    if wait_sec > 0:
        time.sleep(wait_sec + 0.5)
    return next(s for s in valid_snipers if s["alias"] == earliest_alias)

def mark_sniper_cooldown(sniper, cooldown_sec=60):
    if sniper:
        _sniper_cooldown[sniper["alias"]] = time.time() + cooldown_sec

def verify_cas_number(cas_string):
    """[V17.2.3] CAS 踰덊샇 泥댄겕?붿???寃利?肄붿뼱"""
    if not cas_string: return False
    
    # ?슚 [以묒슂] '?곸뾽鍮꾨?'?대굹 '-' ?깆? 寃利앹쓣 ?듦낵?쒖폒???섎?濡??덉쇅 泥섎━
    if any(k in cas_string for k in ["?곸뾽鍮꾨?", "鍮꾧났媛?, "Secret", "Proprietary", "-"]):
        return True
        
    # ?쒖닔 ?レ옄? ?섏씠?덈쭔 異붿텧
    clean_cas = re.sub(r'[^0-9-]', '', cas_string).strip()
    parts = clean_cas.split('-')
    
    if len(parts) != 3: return False
    
    try:
        check_digit = int(parts[2])
        digits = parts[0] + parts[1]
        # 泥댄겕?붿???怨꾩궛 怨듭떇 ?곸슜
        total = sum(int(digit) * i for i, digit in enumerate(reversed(digits), 1))
        return (total % 10) == check_digit
    except:
        return False

def _get_sorted_and_normalized_text(page):
    """[V17.2.3] PyMuPDF ?섏씠吏?먯꽌 ?띿뒪?몃? ?쎄린 ?쒖꽌?濡??뺣젹 諛??뺢퇋?뷀븯??異붿텧"""
    blocks = page.get_text("blocks")
    # y醫뚰몴 -> x醫뚰몴 ?쒖쑝濡??뺣젹 (?쎄린 ?쒖꽌)
    blocks.sort(key=lambda b: (b[1], b[0]))
    text_list = []
    for b in blocks:
        text_list.append(unicodedata.normalize("NFKC", b[4]))
    return "\n".join(text_list)

if not OPENAI_API_KEY:
    print("寃쎄퀬: .env ?뚯씪??OPENAI_API_KEY媛 ?놁뒿?덈떎.")

VERSION = "17.2.3"

EXCEPTION_REGISTRY = {
    "CR-13_SERIES": {
        "triggers": ["?곌컯???쇰났?꾪겕 ?⑹젒遊?, "CS-200", "CR-13"],
        "target_pn": "?⑹젒?щ즺(?곌컯???쇰났?꾪겕 ?⑹젒遊? CR-13",
        "target_substances": "?⑹젒?? ?고솕泥?遺꾩쭊, ??; 留앷컙 諛?洹?臾닿린?뷀빀臾? ?댁궛?뷀떚???,
        "components": "13463-67-7(10~15%); 68476-25-5(5~10%); 7439-96-5(1~5%); 1344-09-8(1~5%); 1317-65-3(1~5%); 12001-26-2(1~5%); 7439-89-6(Rem.%)"
    }
}

def call_gemini_with_retry(payload, initial_sniper, max_retries=8, log_func=None):
    current_sniper = initial_sniper
    for attempt in range(max_retries):
        if not current_sniper:
            raise ValueError("?슚 ?꾨떞 ?ㅻ굹?댄띁媛 諛곗젙?섏? ?딆븯?듬땲??")
            
        api_key = current_sniper["key"]
        alias = current_sniper["alias"]
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
        
        try:
            response = requests.post(url, headers={'Content-Type': 'application/json'}, json=payload, timeout=60)
            if response.status_code != 200:
                if log_func: log_func(f"  ?뵶 {alias} ?ш꺽 ?ㅽ뙣(HTTP {response.status_code})")
                if response.status_code == 429: mark_sniper_cooldown(current_sniper, 60)
                elif response.status_code == 503: mark_sniper_cooldown(current_sniper, 30)
                
                backoff_time = 1.0 + attempt
                time.sleep(backoff_time)
                current_sniper = get_next_sniper()
                continue
            return response.json()
        except requests.exceptions.RequestException as e:
            mark_sniper_cooldown(current_sniper, 30)
            backoff_time = 1.0 + attempt
            time.sleep(backoff_time)
            current_sniper = get_next_sniper()
            continue
    raise Exception(f"?슚 {max_retries}???곗냽 ?ш꺽 ?ㅽ뙣. 遺덈룄?(GPT) ?ъ엯!")

def extract_product_name_hybrid(text_chunk, image_list, current_sniper, log_func=None):
    if not current_sniper or not image_list: return "", "?ㅽ뙣"
    first_page_img = image_list[0]
    b64_data = first_page_img.get("data", "") if isinstance(first_page_img, dict) else first_page_img
    mime_type = first_page_img.get("mime_type", "image/jpeg") if isinstance(first_page_img, dict) else "image/jpeg"

    prompt = """
    ?덈뒗 MSDS???쒗뭹紐낆쓣 ?뺥솗???뺤젙 吏볥뒗 ?꾨Ц ?먮룆愿?대떎. 
    1. [援ъ뿭 寃⑸━]: "1. ?뷀븰?쒗뭹怨??뚯궗??愿???뺣낫" ??ぉ??李얘퀬 洹??꾨옒遺??"2. ?좏빐?굿룹쐞?섏꽦" ?꾧퉴吏留??쎌뼱??
    2. [?듭떖 ?寃?: '媛. ?쒗뭹紐?, '?곹뭹紐?, '?덈챸' ?깆쓽 ?덉씠釉붿씠 媛由ы궎??[?쒖닔 ?쒗뭹紐?留??뺥솗??異붿텧?섎씪. 
    遺덊븘?뷀븳 ?띿뒪?몃뒗 ?쒓굅?섍퀬 ?ㅼ쭅 '?쒗뭹紐? 臾몄옄?대쭔 ????以꾨줈 異쒕젰?섎씪. 紐?李얘쿋?쇰㈃ ?꾨Т寃껊룄 異쒕젰?섏? 留덈씪.
    """
    payload = {"contents": [{"parts": [{"text": prompt}, {"inlineData": {"mimeType": mime_type, "data": b64_data}}]}]}
    try:
        result = call_gemini_with_retry(payload, current_sniper, log_func=log_func)
        if result:
            pn_ai = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
            if pn_ai and not any(k in pn_ai for k in ["誘몄텛異?, "?뺤씤"]) and not re.search(r'[PH]\d{3}', pn_ai):
                if log_func: log_func(f" ?쒋? [?쒗뭹紐??ㅼ틪] ??鍮꾩쟾 ?ㅻ굹?댄븨 ?깃났: {pn_ai[:30]}")
                return pn_ai.replace('\n', ' ').strip(), "Vision"
    except Exception as e:
        pass
    return "", "?ㅽ뙣"

def load_system_prompt():
    prompt_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'prompt_system_v5.txt')
    try:
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except Exception:
        return "?뱀떊? MSDS ?곗씠??異붿텧 ?꾨Ц媛?낅땲??"

SYSTEM_PROMPT_TEXT = load_system_prompt()

# ?슚 [?섏닠 1] 李뚭볼湲??꾨＼?꾪듃 ?뺣━ (?뺤콉 ?숆린?? CAS ?놁쑝硫?異붿텧 嫄곕?)
PROMPT_GEMINI_FLASH = """
?뱀떊? 1李?怨좎냽 ?쒓컖 異붿텧湲?Sniper)?낅땲?? 泥⑤???MSDS ???대?吏留?蹂닿퀬 ?곗씠?곕? 異붿텧?섏꽭??

[?뵦 1李??붿쭊 ?덈? ?먯튃]
1. ?좏슚??CAS 踰덊샇(?뺤떇: ?レ옄-?レ옄-?レ옄)媛 ?녿뒗 ?깅텇(?곸뾽鍮꾨?, -, 鍮덉뭏 ??? ?듭?濡?異붿텧?섏? 留먭퀬 臾댁“嫄????꾩껜瑜??쒖쇅?섎씪.
2. ?ㅼ쨷 CAS ?⑥씪 臾몄옄?댄솕: ??????щ윭 CAS媛 ?덈떎硫??щ옒??/)濡?臾띠뼱??異붿텧?섎씪.
3. ?섍컖 湲덉?: ?쒖뿉 ?녿뒗 ?レ옄瑜?吏?대궡吏 留덈씪. CAS???덈뒗???⑥쑀??移몄씠 鍮꾩뼱?덈떎硫??⑥쑀?됱쓣 '誘멸린??'濡?異쒕젰?섎씪.
4. 遺?깊샇 踰붿쐞 議곗옉 湲덉?: ?먮낯??'0.1-1' ?대㈃ '0.1~1%'濡? ?덉뿉 蹂댁씠??洹몃?濡?異붿텧?섎씪.
5. ?⑥쑀???щ㎎: 紐⑤뱺 ?⑥쑀???ㅼ뿉??諛섎뱶??'%'瑜?遺숈뿬??
"""

PROMPT_GPT_FALLBACK = """?뱀떊? ?뚭눼???쒕? 湲곸뼱紐⑥쑝??2李?遺덈룄?(Bulldozer)?낅땲?? 泥⑤????대?吏???쒖뿉???곗씠?곕? '?덉뿉 蹂댁씠??洹몃?濡? ?⑥닚 臾댁떇?섍쾶 蹂듭궗?섏꽭?? 

[?뵦 遺덈룄? ?⑥닚 異붿텧 4? ?먯튃]
1. ?앷컖 湲덉?: % 湲고샇 遺숈씠湲? 遺?깊샇 援먯젙, '?붾웾'??'Rem.%'濡?諛붽씀湲????대뼚??媛怨듭씠??踰덉뿭???섏? 留덉꽭?? ?꾩냽 ?붿쭊???뚯븘???⑸땲?? ?쒖뿉 ?곹엺 湲?⑤? 洹몃?濡???댄븨?섏꽭??
2. ?곸뾽鍮꾨? 諛?怨듬? ?듦낵: CAS 踰덊샇 移몄뿉 踰덊샇媛 ?녾퀬 '?곸뾽鍮꾨?', '-', '鍮꾧났媛? ?깆씠 ?곹??덈떎硫? 踰꾨━吏 留먭퀬 洹?湲?먮? 洹몃?濡?`cas_no`???곸뼱?ㅼ꽭??
3. ?ㅼ쨷 CAS ?듯빀: ??移몄뿉 CAS 踰덊샇媛 ?щ윭 媛?萸됱퀜 ?덉쑝硫??됱쓣 ?섎늻吏 留먭퀬, ?꾩뼱?곌린???щ옒??/)濡?臾띠뼱????以꾨줈 ?????ㅼ꽭??
4. ?섏씠吏 ?몃옒?? 媛??깅텇??諛쒓껄???대?吏???ㅼ젣 ?섏씠吏 踰덊샇瑜?'page' ?꾨뱶??湲곗옱?섏꽭??

[?뵦 2李??붿쭊 ?덈? ?먯튃]
1. 怨듦컙 吏媛?蹂듦뎄: ?쒖쓽 ?좎씠 ?щ챸?섍굅?? 誘몄꽭?섍쾶 ??댁죱嫄곕굹, 鍮꾨?移??ㅼ쨷 蹂묓빀???덈뜑?쇰룄 ?쒖쓽 ?꾩껜?곸씤 留λ씫???낆껜?곸쑝濡??쎌뼱 CAS? ?⑥쑀?됱쓣 留ㅼ묶?섏꽭??
2. ?슚 ?덈? ?먭린 諛??쒓컖???⑺듃 二쇱쓽: ?쒖뿉 紐낆떆???レ옄濡???CAS 踰덊샇(?뺤떇: ?レ옄-?レ옄-?レ옄)留?異붿텧?섎씪. ?뷀븰 臾쇱쭏紐낆씠??臾몃㎘??蹂닿퀬 ?ㅺ? ?꾨뒗 ?뷀븰 吏?앹쓣 ?숈썝?섏뿬 ?ㅼ〈?섎뒗 CAS 踰덊샇瑜??좎텛?섍굅??吏?대궡??Hallucination) ?됱쐞???덈? 湲덉??쒕떎. ?덉뿉 紐낇솗??蹂댁씠??踰덊샇媛 ?녾굅??'?곸뾽鍮꾨?', '鍮꾧났媛?, '-' ?깆씠?쇰㈃ 媛李??놁씠 洹??됱쓣 異붿텧 ??곸뿉???먭린?섎씪.
3. ?슚 ?щ㎎ ?듭씪 諛??섍컖 諛⑹?: 異붿텧???⑥쑀???レ옄 ?ㅼ뿉??諛섎뱶??'%' 湲고샇瑜?遺숈뿬?? ?? ?먮낯 ?쒖뿉 ?⑥쑀?됱씠 ?レ옄媛 ?꾨땶 '?붾웾', '?섎㉧吏', 'balance', '?곷웾' ?깆쑝濡??쒓린?섏뼱 ?덈떎硫? ?덈? 蹂몄씤 留덉쓬?濡??レ옄(?? 10%)瑜?吏?대궡嫄곕굹 怨꾩궛?댁꽌 ?곸? 留덈씪. 臾댁“嫄??곷Ц ??뚮Ц?먮? 留욎떠 'Rem.%' ?쇰뒗 臾몄옄??洹몃?濡?異쒕젰?섎씪.
   ?슚 遺?깊샇 ?쇱넀 ?덈? 湲덉?: ?먮낯 ?쒖쓽 ?⑥쑀?됱뿉 遺?깊샇(<, ?????띿뒪??誘몃쭔, ?댄븯)媛 ?ы븿?섏뼱 ?덈떎硫? ?대? ?덈? 臾쇨껐??~) 踰붿쐞 湲고샇濡?諛붽씀吏 留덈씪.
   [?щ컮瑜??덉떆]: ?먮낯??'<1' ?대㈃ '<1%'濡?異쒕젰, ?먮낯??'??' ?대㈃ '??%'濡?異쒕젰.
   [?섎せ???덉떆]: ?먮낯??'<1' ?몃뜲 '~1%'濡?蹂議고븯??異쒕젰 (?덈? 湲덉?).

4. ?슚 ?섏씠吏 ?몃옒?? 媛??깅텇??諛쒓껄???섏씠吏 踰덊샇瑜?'page' ?꾨뱶??湲곗옱?섎씪.
 
 JSON 異쒕젰 ?щ㎎:
 {
   "援ъ꽦?깅텇": [
     {"cas_no": "123-45-6 / ?곸뾽鍮꾨?", "content": "10 誘몃쭔", "page": "3"}
   ],
   "援먯젙_?ъ쑀": "?⑥닚 臾댁떇 ?먮낯 ?띿뒪??蹂듭궗 諛??ъ링 蹂듦뎄 ?꾨즺"
 }"""

def _normalize_single_content(content_str):
    """[V17.2.4.1] 留덉씠?덉뒪 ?섏튂 ?ㅻ쪟 ?닿껐 諛??ㅼ썙??誘몃쭔/?댄븯) ?꾨꼍 蹂댁〈 (踰꾧렇 ?섏젙??"""
    orig_raw = str(content_str).strip()
    
    # 1. 湲곗큹 ?뺤젣: ?쇰낯????닚 遺?깊샇 諛??붾웾 ?쒓린 ?듭씪
    v = re.sub(r'([\d\.]+)\s*(<)', r'>\1', orig_raw)
    v = re.sub(r'([\d\.]+)\s*(>)', r'<\1', v)
    v = re.sub(r'(?i)?붾웾|balance|remainder|餘뗫웾|?섎㉧吏', 'Rem.', v)
    
    # 2. ?쒓?/?곷Ц ?ㅼ썙?쒕? 湲고샇濡??좎튂??(?꾨씫 諛⑹?)
    v = re.sub(r'(?i)([0-9.]+)\s*(?:%?)\s*(誘몃쭔|below|less\s*than|?ゆ?)', r'<\1', v)
    v = re.sub(r'(?i)([0-9.]+)\s*(?:%?)\s*(?댄븯|up\s*to|餓δ툔)', r'??1', v)
    v = re.sub(r'(?i)([0-9.]+)\s*(?:%?)\s*(珥덇낵|more\s*than|over|擁?', r'>\1', v)
    v = re.sub(r'(?i)([0-9.]+)\s*(?:%?)\s*(?댁긽|above|餓δ툓)', r'??1', v)

    # 3. 遺덊븘?뷀븳 ?⑥쐞 諛?怨듬갚 ?쒓굅
    v = v.replace(" ", "")
    v = re.sub(r'(?i)\(w/w\)|\(v/v\)|\(w/v\)|\(weight/weight\)|proprietary|secret', '', v)
    if re.search(r'(?i)(mg/m3|mg/l|g/l|ppm|kg|ml|쨉g|ug)', v): return "誘멸린??"
    v = v.replace('竊?, '<').replace('竊?, '>').replace('<=', '??).replace('>=', '??)

    # 4. 짹 湲고샇 ?곗궛 (?ㅻ쫫李⑥닚 蹂댁옣) - [?⑥튂] ?⑥씪 ?섏씠??-)? 踰붿쐞濡??묐낫
    pm_match = re.search(r'([0-9.]+)\s*(?:짹|\+\s*-\s*|\+/?-)\s*([0-9.]+)', v)
    if pm_match:
        try:
            val, pm = float(pm_match.group(1)), float(pm_match.group(2))
            n1, n2 = sorted([val-pm, val+pm])
            return f"{n1:g}~{n2:g}%"
        except: pass

    # 5. 踰붿쐞 ?⑦꽩 (?レ옄 ~ ?レ옄) 異붿텧 - [?⑥튂] 留덉묠???⑤룆 ?몄떇 諛⑹? (?レ옄 ?꾩닔)
    range_m = re.search(r'([<>?ㅲ돟]*)\s*(\d*\.?\d+)\s*[-~?쇽퐵/]\s*([<>?ㅲ돟]*)\s*(\d*\.?\d+)', v)
    if range_m:
        p1, n1, p2, n2 = range_m.groups()
        try:
            # ?슚 [V17.2.4 ?듭떖] ?レ옄留?鍮꾧탳?댁꽌 ?ㅼ쭛? ?덉쑝硫??ㅼ솑
            if float(n1) > float(n2):
                n1, n2 = n2, n1
                p1, p2 = p2, p1 # 遺?깊샇???곕씪媛?            # 源⑤걮?섍쾶 議곕┰ (遺덊븘?뷀븳 遺?깊샇 以묐났 ?쒓굅)
            res = f"{p1}{n1}~{p2}{n2}"
            return res if '%' in res else res + '%'
        except: pass

    # 6. ?⑥씪 ?섏튂 ?⑦꽩 (遺?깊샇 ?ы븿) - [?⑥튂] 留덉묠???⑤룆 ?몄떇 諛⑹? (?レ옄 ?꾩닔)
    single_m = re.search(r'([<>?ㅲ돟]?)\s*(\d*\.?\d+)', v)
    if single_m:
        p, n = single_m.groups()
        return f"{p}{n}%"

    if "Rem" in v: return "Rem.%"
    return "誘멸린??"
        
    return "誘멸린??"


def final_quality_control(components, full_text, is_ai=True, log_func=None):
    """[V17.2.1] Fuzzy Shield 3?④퀎 ?곸슜 Grounding"""
    refined_dict = {}  
    has_invalid = False
    norm_text = re.sub(r'\s+', '', full_text).upper() if full_text else ""
    
    for comp in components:
        raw_cas_field = str(comp.get("cas", "") or comp.get("cas_no", "")).strip()
        cas_list = re.findall(r'(?<![\d-])(\d{1,7}-\d{2}-\d)(?![\d-])', raw_cas_field)
        
        if not cas_list: continue

        raw_content = str(comp.get("content", "")).strip()
        content_parts = [_normalize_single_content(c) for c in re.split(r'\s*/\s*', raw_content) if c.strip()]
        page_val = comp.get("page", "")
        origin_engine = comp.get("engine", "Unknown") # DNA 瑗щ━???좎?
        
        loop_content = content_parts if len(cas_list) == len(content_parts) else [content_parts[0] if content_parts else ""] * len(cas_list)
        
        for cas_raw, cv in zip(cas_list, loop_content):
            cas = re.sub(r'^0+', '', cas_raw)
            if not verify_cas_number(cas):
                has_invalid = True
                continue
                
            if is_ai and norm_text:
                # 1?④퀎: ?꾧꺽 留ㅼ묶 (Strict)
                if cas not in norm_text:
                    # 2?④퀎: ?섏씠???쒓굅 留ㅼ묶 (Soft)
                    cas_no_hyphen = cas.replace('-', '')
                    norm_text_no_hyphen = norm_text.replace('-', '')
                    
                    if cas_no_hyphen not in norm_text_no_hyphen:
                        # ?슚 [?섏닠 2] 3?④퀎: Fuzzy Shield (OCR ?몄씠利?媛뺤젣 移섑솚 留ㅼ묶)
                        fuzzy_trans = str.maketrans('SOIlBZsbo', '501182560')
                        fuzzy_text = norm_text_no_hyphen.translate(fuzzy_trans)
                        fuzzy_cas = cas_no_hyphen.translate(fuzzy_trans)
                        
                        if fuzzy_cas not in fuzzy_text:
                            if log_func: log_func(f" ?좑툘 [Grounding 諛⑹뼱] 3?④퀎 ?쇱? ?대뱶 遺뺢눼. ?섍컖 CAS ?곴뎄 ?먭린: {cas}")
                            has_invalid = True
                            continue # ?쇱????ㅽ뙣?섎㈃ ?ъ궡!

            if cv:
                if cas not in refined_dict:
                    refined_dict[cas] = {"cas": cas, "content": cv, "page": page_val, "engine": origin_engine}

    refined = list(refined_dict.values()) 
    if is_ai:
        try: check_omission(full_text, refined)
        except ValueError as e:
            if log_func: log_func(f" ?윞 [?꾨씫 媛먯?] {e}")
            has_invalid = True 
        
    return refined, has_invalid

def find_section3_pages(doc):
    pages = []
    for i in range(len(doc)):
        text = doc[i].get_text("text")
        if re.search(r'(?:SECTION\s*)?[23][\s.:]*(?:援ъ꽦|?깅텇|?⑥쑀|COMPOSITION|INGREDIENTS)', text, re.I):
            if i not in pages: pages.append(i)
        if pages and re.search(r'(?:SECTION\s*)?[34][\s.:]*(?:?묎툒|?좏빐???꾪뿕??FIRST|HAZARDS)', text, re.I):
            if i not in pages: pages.append(i)
            break 
    return pages

def extract_section3_images(pdf_path, current_sniper, log_func=None):
    try:
        doc = fitz.open(pdf_path)
        pages = find_section3_pages(doc)
        
        # ?슚 [?섏닠 3] 吏???뺤같(Lazy Recon) ?몃옪: ?띿뒪?몃줈 紐?李얠쑝硫??ㅼ틪蹂몄쑝濡?媛꾩＜?섍퀬 鍮꾩쟾 ?뺤같 ?ъ엯
        if not pages:
            if log_func: log_func(" ?뵇 ?띿뒪???먯? ?ㅽ뙣 (?먮뒗 ?ㅼ틪蹂?. 鍮꾩쟾 ?뺤같蹂?Recon) 媛??..")
            recon_images = []
            for i in range(min(5, len(doc))):
                pix = doc[i].get_pixmap(matrix=fitz.Matrix(0.8, 0.8))
                recon_images.append({"mimeType": "image/png", "data": base64.b64encode(pix.tobytes("png")).decode("utf-8")})
            
            recon_res = call_gemini_2_5_flash(recon_images, prompt="???대?吏??以?'2. 援ъ꽦?깅텇' ?먮뒗 '3. 援ъ꽦?깅텇' ?쒓? ?덈뒗 ?섏씠吏 踰덊샇(0遺???쒖옉)瑜?李얠븘?? JSON?묐떟: {\"page_index\": ?レ옄}", current_sniper=current_sniper, log_func=log_func)
            page_idx = int(recon_res.get("page_index", -1)) if recon_res else -1
                
            if 0 <= page_idx < len(doc):
                pages = [page_idx, page_idx + 1] if page_idx + 1 < len(doc) else [page_idx]
                if log_func: log_func(f" ?렞 ?뺤같蹂묒씠 ?섏씠吏瑜?李얠븯?듬땲?? {pages}踰?諛붿씤??)
            else:
                doc.close()
                return [], "", []

        images, raw_text = [], ""
        for p_idx in pages:
            if p_idx >= len(doc): continue
            page = doc[p_idx]
            raw_text += _get_sorted_and_normalized_text(page) + "\n"
            pix = page.get_pixmap(matrix=fitz.Matrix(2.5, 2.5))
            images.append({"mimeType": "image/png", "data": base64.b64encode(pix.tobytes("png")).decode("utf-8")})
            if len(images) >= 3: break
            
        doc.close()
        
        section3_text_only = raw_text
        start_m = re.search(r'(?:SECTION\s*)?[23][\s.:]*(?:援ъ꽦|COMPOSITION)', raw_text, re.I)
        if start_m:
            end_m = re.search(r'(?:SECTION\s*)?[34][\s.:]*(?:?묎툒|?좏빐???꾪뿕??FIRST|HAZARDS)', raw_text[start_m.end():], re.I)
            section3_text_only = raw_text[start_m.start():start_m.end() + end_m.start()] if end_m else raw_text[start_m.start():]

        return images, section3_text_only, pages 
    except Exception:
        return [], "", []

def call_gemini_2_5_flash(image_list=None, prompt=None, current_sniper=None, log_func=None):
    if not image_list or not current_sniper: return None
    final_prompt = prompt if prompt else PROMPT_GEMINI_FLASH
    parts = [{"text": f"{SYSTEM_PROMPT_TEXT}\n\n{final_prompt}"}]
    for img in image_list:
        parts.append({"inlineData": {"mimeType": "image/png", "data": img.get("data", "")}})
    payload = {"contents": [{"parts": parts}], "generationConfig": {"temperature": 0.0, "responseMimeType": "application/json"}}
    try:
        result = call_gemini_with_retry(payload, current_sniper, log_func=log_func)
        if result:
            text_response = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            return json.loads(text_response)
    except: pass
    return None

def check_omission(original_text, extracted_data):
    if not original_text: return 
    cas_pattern = re.compile(r'(?<![\d-])(\d{1,7}-\d{2}-\d)(?![\d-])')
    unique_cas_found = list(set(cas_pattern.findall(original_text)))
    valid_original_cas = [cas for cas in unique_cas_found if verify_cas_number(cas)]
    original_cas_count = len(valid_original_cas)
    
    extracted_cas_set = set()
    for c in (extracted_data if isinstance(extracted_data, list) else extracted_data.get("援ъ꽦?깅텇", [])):
        found = cas_pattern.findall(str(c.get("cas") or c.get("cas_no") or ""))
        extracted_cas_set.update([f for f in found if verify_cas_number(f)])
    
    if len(extracted_cas_set) < original_cas_count:
        raise ValueError(f"?ㅻ굹?댄띁 ?꾨씫 諛쒖깮 (?먮낯:{original_cas_count} vs 異붿텧:{len(extracted_cas_set)}). 2李??붿썝 ?ъ엯!")

def call_gpt_4o_mini(image_list=None, prompt=None, log_func=None):
    if not image_list or not OPENAI_API_KEY: return None
    final_prompt = prompt if prompt else PROMPT_GPT_FALLBACK
    content_list = [{"type": "text", "text": final_prompt}]
    for img in image_list:
        content_list.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img.get('data', '')}"}})
    payload = {"model": "gpt-4o-mini", "messages": [{"role": "system", "content": SYSTEM_PROMPT_TEXT}, {"role": "user", "content": content_list}], "temperature": 0.0, "response_format": {"type": "json_object"}}
    try:
        response = requests.post("https://api.openai.com/v1/chat/completions", headers={"Content-Type": "application/json", "Authorization": f"Bearer {OPENAI_API_KEY}"}, json=payload, timeout=60)
        if response.status_code == 200: return json.loads(response.json()["choices"][0]["message"]["content"])
    except: pass
    return None

def _clean_content_odl(text):
    t = text.replace(" ", "")
    if any(k in t.lower() for k in ["balance", "?붾웾", "rem"]): return "Rem.%"
    return t

def parse_row_robust_v2(row):
    """[V17.2.2] 媛????⑤웾 ?먮퀎湲??꾩엯 諛?EC/KE踰덊샇 ?섏씠?ы궧 ?꾨꼍 李⑤떒"""
    cells = [re.sub(r'\s+', ' ', (c.text or "")).strip() for c in row.cells if (c.text or "").strip()]
    if len(cells) < 2: return None

    header_keywords = {"cas", "casno", "cas踰덊샇", "cas-no", "?⑥쑀??, "?⑤웾", "content", "援ъ꽦?깅텇", "?뷀븰臾쇱쭏紐?, "substance", "臾쇱쭏紐?, "紐낆묶"}
    cell_lower_set = {re.sub(r'[\s\(\)\.%]', '', c.lower()) for c in cells}
    if cell_lower_set.intersection(header_keywords): return None

    cas_list, name_candidates = [], []
    strong_content = None # ?뺤떎???⑤웾 (%, ~, <, ?뚯닔?????ы븿)
    weak_content = None   # 遺덊솗?ㅽ븳 ?⑤웾 (?⑥닚 ?뺤닔, ?몃뜳??踰덊샇??媛?μ꽦)

    for c in cells:
        # 1. CAS 寃異?        found_cas = re.findall(r'(?<![\d-])(\d{1,7}-\d{2}-\d)(?![\d-])', c)
        if found_cas:
            cas_list.extend(found_cas)
            # CAS? ?⑤웾????移몄뿉 萸됱퀜?덈뒗 ?ｌ? 耳?댁뒪 諛⑹뼱
            c_remain = re.sub(r'(?<![\d-])(\d{1,7}-\d{2}-\d)(?![\d-])', '', c).strip()
            if not c_remain:
                continue
            c = c_remain # ?⑥? 李뚭볼湲곕줈 ?⑤웾 寃???랁뻾

        # 2. ?슚 [?듭떖] ?⑤웾 寃異? ?섎Ц???뺢퇋???⑥닔)???듦낵??吏꾩쭨 ?⑤웾留?諛쏆쓬
        norm_c = _normalize_single_content(c)
        if norm_c != "誘멸린??":
            # EC踰덊샇 ?깆? ?뺢퇋???⑥닔?먯꽌 誘멸린??濡?嫄몃윭???닿납??吏꾩엯?섏? 紐삵븿!
            if any(k in c for k in ['%', '~', '-', '<', '>', '??, '??, '.', 'Rem', '?붾웾', 'balance']):
                if not strong_content: strong_content = _clean_content_odl(c)
            else:
                if not weak_content: weak_content = _clean_content_odl(c)
            continue

        # 3. 臾쇱쭏紐??꾨낫
        if len(c) > 1 and not re.match(r'^[\d\s.,\-~]+$', c):
            name_candidates.append(c)

    if not cas_list: return None

    name = ""
    if name_candidates:
        valid_names = [n for n in name_candidates if len(n) < 50]
        name = max(valid_names, key=len) if valid_names else name_candidates[0]

    # Strong(?뺤떎???⑤웾)???곗꽑, ?놁쑝硫?Weak(?뺤닔), ???놁쑝硫?誘멸린??
    final_content = strong_content or weak_content or "誘멸린??"

    final_comps = []
    for cas in cas_list:
        final_comps.append({
            "name": name,
            "cas_no": cas,
            "content": final_content,
            "engine": "ODL-v2.2"
        })
    return final_comps

def extract_components_odl_robust(odl_doc, target_pages):
    components = []
    if not target_pages or not odl_doc or not odl_doc.pages: return components

    for p_idx in target_pages:
        if p_idx >= len(odl_doc.pages): continue
        tables = [el for el in getattr(odl_doc.pages[p_idx], 'elements', []) if getattr(el, 'type', '') == "TABLE"]
        for table in tables:
            for row in table.rows:
                parsed_comps = parse_row_robust_v2(row)
                if parsed_comps: components.extend(parsed_comps)
    return components

# ?슚 [?섏닠 6] ?몃え?녿뒗 ?곕뱶 肄붾뱶(fallback_text_extraction) ?꾨꼍 ?뚭컖 ?꾨즺!

def process_pdf(pdf_path, log_func=None):
    start_time = time.time()
    current_sniper = get_next_sniper()
    alias = current_sniper["alias"] if current_sniper else "?뚯닔?놁쓬"
    
    if log_func: log_func(f" ?? [V17.2.3] ?붿쭊 媛?? {os.path.basename(pdf_path)}")

    image_list, section3_text, pages = extract_section3_images(pdf_path, current_sniper, log_func=log_func)
    
    full_text_for_grounding = ""
    try:
        doc = fitz.open(pdf_path)
        first_page_text = _get_sorted_and_normalized_text(doc[0]) if len(doc) > 0 else ""
        for page in doc: full_text_for_grounding += _get_sorted_and_normalized_text(page)
        pix_cover = doc[0].get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
        cover_img = [{"mimeType": "image/png", "data": base64.b64encode(pix_cover.tobytes("png")).decode("utf-8")}]
        doc.close()
    except:
        cover_img, first_page_text, full_text_for_grounding = image_list, "", ""
        
    hybrid_pn, _ = extract_product_name_hybrid(first_page_text, cover_img, current_sniper, log_func=log_func)

    used_engine = ""
    is_ai_extracted = False
    ai_res = None
    
    doc_t = fitz.open(pdf_path)
    target_pages = find_section3_pages(doc_t) 
    doc_t.close()

    try:
        parser = PDFParser()
        odl_doc = parser.parse(pdf_path)
        odl_components = extract_components_odl_robust(odl_doc, target_pages)
    except Exception as e:
        if log_func: log_func(f" ?좑툘 ODL ?뚯떛 ?ㅻ쪟: {e}")
        odl_components = []
    
    pure_odl_cas = sum(1 for c in odl_components if re.search(r'\d-\d', str(c.get("cas", "") or c.get("cas_no", ""))))
    
    # ?슚 吏???뺤같 ?곌퀎: ODL???꾨Т寃껊룄 紐?李얠븯?붾뜲 target_pages???덉뿀?ㅻ㈃ ?ㅼ틪蹂??뺣쪧 ?믪쓬
    if pure_odl_cas > 0:
        if log_func: log_func(f" ?윟 ODL ?뺣? 異붿텧 ?깃났 ({len(odl_components)}嫄?. AI ?앸왂.")
        ai_res = {"援ъ꽦?깅텇": odl_components, "援먯젙_?ъ쑀": "ODL ?뺣? 異붿텧 ?꾨즺"}
        used_engine = "ODL-Regex"
        is_ai_extracted = False
    else:
        if log_func: log_func(f" ?윞 ODL ?먯? 0嫄????놁쓬/?ㅼ틪蹂?. AI 鍮꾩쟾 ?ㅻ굹?댄띁({alias}) ?ъ엯!")
        ai_res = call_gemini_2_5_flash(image_list, PROMPT_GEMINI_FLASH, current_sniper, log_func)
        used_engine = "Gemini-Flash"
        is_ai_extracted = True
        
        # ?슚 [?섏닠 5] DNA 瑗щ━??遺李?(Gemini)
        if ai_res and "援ъ꽦?깅텇" in ai_res:
            for c in ai_res["援ъ꽦?깅텇"]: c["engine"] = used_engine
            pure_cas_count = sum(1 for c in ai_res.get("援ъ꽦?깅텇", []) if re.findall(r'(?<![\d-])(\d{1,7}-\d{2}-\d)(?![\d-])', str(c.get("cas", "") or c.get("cas_no", ""))))
        else: pure_cas_count = 0
            
        if not ai_res or "援ъ꽦?깅텇" not in ai_res or pure_cas_count == 0:
            if log_func: log_func(" ?쒋? [Step 3] AI Bulldozer (GPT-4o-mini) 蹂듦뎄 ?ъ엯...")
            ai_res = call_gpt_4o_mini(image_list, PROMPT_GPT_FALLBACK, log_func=log_func)
            used_engine = "GPT-4o-mini"
            is_ai_extracted = True
            
            # ?슚 [?섏닠 5] DNA 瑗щ━??遺李?(GPT)
            if ai_res and "援ъ꽦?깅텇" in ai_res:
                for c in ai_res["援ъ꽦?깅텇"]: c["engine"] = used_engine
                pure_cas_count = sum(1 for c in ai_res.get("援ъ꽦?깅텇", []) if re.findall(r'(?<![\d-])(\d{1,7}-\d{2}-\d)(?![\d-])', str(c.get("cas", "") or c.get("cas_no", ""))))
            else: pure_cas_count = 0
                
            if not ai_res or "援ъ꽦?깅텇" not in ai_res or pure_cas_count == 0:
                if log_func: log_func(" ??AI ?붿쭊留덉? 異붿텧 ?ㅽ뙣 (?섎룞 寃?????")
                return {"error": "?꾩껜 異붿텧 ?ㅽ뙣 (?섎룞 寃???꾩슂)", "?쒗뭹紐?: hybrid_pn, "?좏샇??: "?뵶"}

    components = ai_res.get("援ъ꽦?깅텇", [])
    reason = ai_res.get("援먯젙_?ъ쑀", "?ъ쑀 ?놁쓬")
    
    local_grounding_text = str(first_page_text)
    try:
        doc_g = fitz.open(pdf_path)
        for p_idx in pages:
            if p_idx != 0: local_grounding_text += "\n" + _get_sorted_and_normalized_text(doc_g[p_idx])
        doc_g.close()
    except: local_grounding_text += "\n" + str(section3_text)
    
    refined_comps, has_invalid_cas = final_quality_control(components, local_grounding_text, is_ai=is_ai_extracted, log_func=log_func)
    
    comp_parts = [f"{c['cas']}({c['content']})" for c in refined_comps]
    if not comp_parts:
        if log_func: log_func(" ???좏슚???깅텇 ?곗씠?곌? 議댁옱?섏? ?딆쓬")
        return {"error": "AI 異붿텧 ?꾩쟾 ?ㅽ뙣 (?섎룞 寃???꾩슂)", "?쒗뭹紐?: hybrid_pn, "?좏샇??: "?뵶"}

    comp_str = "; ".join(comp_parts)
    product_name = hybrid_pn
    target_substances = ""
    
    norm_search_pool = re.sub(r'[\s\-]', '', product_name + " " + first_page_text[:500]).upper()
    for ext_key, ext_data in EXCEPTION_REGISTRY.items():
        if all(re.sub(r'[\s\-]', '', trigger).upper() in norm_search_pool for trigger in ext_data["triggers"]):
            product_name, comp_str, target_substances = ext_data["target_pn"], ext_data["components"], ext_data["target_substances"]
            break

    gui_engine_name = "flash" if "Gemini" in used_engine else "bulldozer" if "GPT" in used_engine else "odl"
    
    res_obj = {
        "援ъ꽦?깅텇": comp_str, "?쒗뭹紐?: product_name, "痢≪젙???: target_substances,
        "援먯젙_?ъ쑀": reason,
        "?좏샇??: "?윞" if has_invalid_cas or not product_name else "?윟",
        "used_engine": gui_engine_name
    }
    
    if log_func: log_func(f" ??[V17.2.3] ?꾨즺 (?붿쭊: {used_engine}, ?뚯슂?쒓컙: {time.time()-start_time:.2f}珥?")
    return res_obj

analyze_msds = process_pdf

def self_test_regression():
    assert _normalize_single_content("??5%??00%") == "95~100%", "?뚭? ?ㅻ쪟: ?묐갑??遺?깊샇 ?뚭눼"
    assert _normalize_single_content("77.08g") == "誘멸린??", "?뚭? ?ㅻ쪟: ?⑥쐞(g) ?섍컖 ?꾪꽣 ?뚭눼"
    print("[OK] V17.2.3 ?붿쭊 ?먭? 寃利??꾨즺.")

self_test_regression()
