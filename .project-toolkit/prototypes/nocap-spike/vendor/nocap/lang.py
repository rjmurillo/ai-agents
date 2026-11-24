"""Claims in Chinese, Thai and Spanish, for the kinds the ledger can check: tests, push, merge, deploy.

Deterministic and stdlib only, like claims.py. A clause is cut into pieces at CJK / Thai / Latin punctuation and each
piece is read on its own. A piece that is negated, future, conditional, hedged or a question is not a claim (each
language has its own near-miss words). Completion phrases these patterns can't map to a kind ("搞定了", "เสร็จแล้ว",
"listo", and a few phrases in Japanese, Korean, Russian, German, French and Portuguese) become an `unchecked` claim:
recorded as a hidden 🤔 for /nocap all, never silently dropped and never stamped.

Every pattern is linear (bounded repeats, no nested quantifiers); tests/test_redos.py feeds them 100 KB of CJK and
Thai adversarial input.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

CJK_RE = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7af]")
THAI_RE = re.compile(r"[\u0e00-\u0e7f]")
NON_LATIN_RE = re.compile(r"[\u0400-\u04ff\u0e00-\u0e7f\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7af]")
# The two hint patterns run on lowercased text without IGNORECASE, and every branch starts with a plain literal
# ("\bsub" is written s(?<!\ws)ub): `re` then skips, in C, every position whose character can't start a branch.
# With (?i) and a leading \b, each pattern tried every branch at each of 100 K positions (14-19 ms per scan, run
# on every clause; tests/test_redos.py). Use _es_hint / _other_hint, which lowercase first.
ES_HINT_RE = re.compile(r"prueba|t(?<!\wt)ests? (?:pasa|pasaron)|hice push|s(?<!\ws)ub[ií]\b|he subido|fusion|merge[eé]|despleg|"
                        r"desplieg|producci[oó]n|integr[eé]|listo|hecho|terminad|termin[eé]|arregl|resuelt|solucion|correg")
OTHER_HINT_RE = re.compile(r"erledigt|fertig|behoben|gepusht|gemergt|termin[ée]|corrig[ée]|pouss[ée]|fusionn[ée]|"
                           r"d[ée]ploy[ée]|conclu[ií]d|corrigid|feito|mesclad|implantad")


def _es_hint(text: str) -> bool:
    return ES_HINT_RE.search(text.lower()) is not None


def _other_hint(text: str) -> bool:
    return OTHER_HINT_RE.search(text.lower()) is not None


# Pieces: a run of text up to and including one sentence or clause mark (。！？；，、 , ; ! ? and Thai space runs).
PIECE_RE = re.compile(r"[^。！？；，、,;!?\n]{1,400}[。！？；，、,;!?]?")
BRANCH_RE = r"`?(?:origin/|upstream/)?([A-Za-z0-9][A-Za-z0-9_./-]{0,80})`?"
PR_NUM = r"(?:PR|pr|Pr|MR|mr|拉取请求|合并请求)?\s{0,2}#?\s{0,2}(\d{1,7})"

# ---- Chinese -----------------------------------------------------------------------------------------------------
ZH = {
    "tests": re.compile(r"(?:(?:所有|全部|整个|全量)的?)?(?:单元|集成)?测试(?:用例)?(?:已经?|都|均|全部|全都|也){0,3}(?:通过|跑通|过了|全绿)|"
                        r"全部通过|都通过了|均已通过|全绿"),
    "pushed": re.compile(r"(?:已经?|已)(?:将?[\u4e00-\u9fff]{0,6})?推送(?:到|至)?\s{0,2}(?:" + BRANCH_RE + r")?|"
                         r"推送(?:到|至)\s{0,2}" + BRANCH_RE + r"\s{0,2}(?:了|完成|成功)|推送(?:完成|成功)|推送了|"
                         r"(?:已经?|已)push(?:到|至)?\s{0,2}(?:" + BRANCH_RE + r")?|push(?:到|至)\s{0,2}" + BRANCH_RE +
                         r"\s{0,2}了"),
    "merged": re.compile(r"(?:已经?|已)(?:将?[\u4e00-\u9fff]{0,6})?(?:合并|合入|merge)(?:了)?\s{0,2}(?:" + PR_NUM + r")?|"
                         r"(?:PR|pr|MR)\s{0,2}#?(\d{1,7})\s{0,2}(?:已经?|已)(?:被)?(?:合并|合入)|合并了\s{0,2}(?:" + PR_NUM + r")?|"
                         r"(?:合并|合入)(?:完成|成功)"),
    "deployed": re.compile(r"(?:已经?|已)(?:[\u4e00-\u9fff]{0,6})?(?:部署|上线|发布)|部署(?:完成|成功|好了)|上线了|发布到生产"),
}
ZH_DONE = re.compile(r"(?:已经?|都)?(?:完成|搞定|修复|修好|改好|做好|弄好)了|已(?:经)?(?:完成|修复)|大功告成")
ZH_ZERO = re.compile(r"没有(?:任何)?(?:失败|错误)|无(?:失败|错误)|0\s{0,2}个?(?:失败|错误)")
ZH_NEAR = re.compile(r"没有|没|未|不|尚未|还没|无法|失败|"  # negation
                     r"将会|将要|(?<!已)将(?=[\u4e00-\u9fff]{0,3}(?:推送|合并|部署|上线|发布|运行|测试))|会|要|准备|打算|稍后|"
                     r"待会|计划|即将|马上|下一步|"  # future
                     r"如果|假如|若|一旦|只要|等到|"  # conditional
                     r"应该|可能|也许|大概|似乎|好像|估计|理论上|"  # hedge
                     r"吗|是否|有没有|是不是|了没|[？?]|"  # question
                     r"你说|他说|她说|据说|据|报告说|昨天|上周|之前|以前|原来|本来|曾经|"  # someone else, or another time
                     r"请|确认|确保|检查|务必|需要|必须|希望|"  # a request or a wish, not a report
                     r"(?<!全)部分|一些|有些|只有|仅")  # only some of them

# ---- Thai --------------------------------------------------------------------------------------------------------
TH = {
    "tests": re.compile(r"(?:การ)?(?:ทดสอบ|เทสต์|เทส|test(?:s)?)[^\n，。,.!?]{0,40}?ผ่าน|ผ่านการทดสอบ"),
    "pushed": re.compile(r"(?:push|พุช|พุชโค้ด)\s{0,2}(?:โค้ด)?\s{0,2}(?:ขึ้น|ไป(?:ที่|ยัง)?|เข้า)?\s{0,2}(?:" + BRANCH_RE +
                         r")?\s{0,2}(?:แล้ว|เรียบร้อย|เสร็จ|สำเร็จ)"),
    "merged": re.compile(r"(?:merge|เมิร์จ|เมิร์ก|เมิร์ช)\s{0,2}(?:" + PR_NUM + r")?\s{0,2}(?:เข้า\s{0,2}" + BRANCH_RE +
                         r")?\s{0,2}(?:แล้ว|เรียบร้อย|เสร็จ)|รวม\s{0,2}(?:PR|pr)\s{0,2}#?(\d{1,7})?\s{0,2}(?:แล้ว|เรียบร้อย)"),
    "deployed": re.compile(r"(?:deploy|ดีพลอย|ดีพลอยด์)\s{0,2}[^\s]{0,30}?\s{0,2}(?:แล้ว|เรียบร้อย|เสร็จ)|"
                           r"ขึ้น\s{0,2}(?:production|prod|โปรดักชัน|โปรดักชั่น)\s{0,2}(?:แล้ว|เรียบร้อย)"),
}
TH_DONE = re.compile(r"เสร็จ(?:แล้ว|เรียบร้อย)|แก้(?:ไข)?(?:เสร็จ|เรียบร้อย)|เรียบร้อยแล้ว|ทำ(?:เสร็จ|เรียบร้อย)แล้ว|แก้แล้ว")
TH_ZERO = re.compile(r"ไม่มี(?:การ|ตัวไหน|อันไหน)?(?:ที่)?\s{0,2}(?:ล้มเหลว|พัง|ข้อผิดพลาด|fail\w{0,6}|error\w{0,6})")
TH_NEAR = re.compile(r"ไม่|ยังไม่|มิได้|ล้มเหลว|"  # negation
                     r"จะ|กำลังจะ|เดี๋ยว|ต่อไป|ภายหลัง|อีกสักครู่|"  # future
                     r"ถ้า|หาก|เมื่อไหร่|"  # conditional
                     r"น่าจะ|อาจ|คงจะ|คาดว่า|ดูเหมือน|"  # hedge
                     r"ไหม|มั้ย|หรือเปล่า|หรือยัง|รึยัง|ใช่ไหม|[？?]|"  # question
                     r"คุณบอก|เขาบอก|บอกว่า|เมื่อวาน|ก่อนหน้านี้|เคย|"  # someone else, or another time
                     r"ช่วย|กรุณา|โปรด|ต้อง|หวังว่า|"  # a request or a wish, not a report
                     r"บางส่วน|บางตัว|บางอัน|แค่|เพียง")  # only some of them

# ---- Spanish -----------------------------------------------------------------------------------------------------
ES = {
    "tests": re.compile(r"(?i)\b(?:todas\s+)?(?:las\s+)?pruebas(?:\s+[\wáéíóúñ]+){0,2}?\s+(?:pasan|pasaron|han pasado|"
                        r"est[aá]n en verde|salieron bien)\b|\b(?:todos\s+)?(?:los\s+)?tests?\s+(?:pasan|pasaron|han pasado)\b|"
                        r"\bla suite (?:pasa|pas[oó]|est[aá] en verde)\b"),
    "pushed": re.compile(r"(?i)\b(?:hice|he hecho|ya hice)\s+(?:el\s+)?push\b(?:[^.]{0,30}?\b(?:a|al|en)\s+(?:la rama\s+)?"
                         + BRANCH_RE + r")?|\b(?:sub[ií]|he subido|pushe[eé]|push[eé]|empuj[eé]|he empujado)\b"
                         r"(?:[^.]{0,30}?\b(?:a|al|en)\s+(?:la rama\s+)?" + BRANCH_RE + r")?"),
    "merged": re.compile(r"(?i)\b(?:fusion[eé]|he fusionado|merge[eé]|hice (?:el\s+)?merge(?: de)?|integr[eé]|"
                         r"he integrado)\b(?:[^.]{0,30}?#\s{0,2}(\d{1,7}))?|\b(?:el\s+)?pr\s{0,2}#?\s{0,2}(\d{1,7})\s+"
                         r"(?:est[aá]|fue|ha sido|qued[oó])\s+(?:fusionado|mergeado|integrado)\b"),
    "deployed": re.compile(r"(?i)\b(?:desplegu[eé]|he desplegado|hice (?:el\s+)?deploy|(?:ya\s+)?est[aá] desplegad[oa]|"
                           r"desplegad[oa] (?:en|a)|publicad[oa] en producci[oó]n|(?:ya\s+)?est[aá] en producci[oó]n)\b"),
}
ES_DONE = re.compile(r"(?i)\b(?:listo|hecho|terminado|completado|arreglado|resuelto|ya est[aá]|he terminado|termin[eé]|"
                     r"arregl[eé]|solucion[eé]|correg[ií])\b")
ES_ZERO = re.compile(r"(?i)\b(?:sin|ning[uú]n|ninguna|cero|0)\s+(?:fallos?|errores?|fallas?|pruebas fallidas)\b|"
                     r"\b(?:nada|ninguna) fall[oó]\b")
ES_NEAR = re.compile(r"(?i)\bno\b|\bnunca\b|\bningun[ao]?\b|\btodav[ií]a\b|\ba[uú]n no\b|\bsin\b|\bfall\w{0,6}|"  # negation
                     r"\bvoy a\b|\bvamos a\b|\bva a\b|\bvan a\b|\b\w{1,12}(?:ar|er|ir)(?:é|á|án|emos)(?!\w)|\bhar(?:é|á|án|emos)(?!\w)|"
                     r"\bdespu[eé]s\b|\bluego\b|\bm[aá]s tarde\b|\btengo que\b|\bhay que\b|"  # future
                     r"\bsi\b|\bcuando\b|\buna vez que\b|\ben cuanto\b|"  # conditional
                     r"\bquiz[aá]s?\b|\btal vez\b|\bprobablemente\b|\bcreo que\b|\bparece\b|\bsupongo\b|\bdeber[ií]a\w{0,2}|"
                     r"\bpodr[ií]a\w{0,2}|"  # hedge
                     r"[¿?]|"  # question
                     r"\bdijiste\b|\bdijo\b|\bseg[uú]n\b|\bayer\b|\bantes\b|\banteriormente\b")  # someone else / another time

# ---- completion phrases in languages with no checker: hidden 🤔 ---------------------------------------------------
OTHER_DONE = re.compile(r"完了しました|完了です|成功しました|通りました|通過しました|合格しました|プッシュしました|マージしました|デプロイしました|"
                        r"완료(?:했습니다|되었습니다|됐습니다)|통과했습니다|푸시했습니다|병합했습니다|배포했습니다|"
                        r"(?i:\bготово\b|\bсделано\b|\bисправил[аи]?\b|\bзапушил[аи]?\b|\bсмержил[аи]?\b|\bзадеплоил[аи]?\b|"
                        r"\bтесты прошли\b|\berledigt\b|\bfertig\b|\bbehoben\b|\bgepusht\b|\bgemergt\b|\bterminé\b|\bcorrigé\b|"
                        r"\bpoussé\b|\bfusionné\b|\bdéployé\b|\bconcluído\b|\bcorrigido\b|\bimplantado\b)")
OTHER_NEAR = re.compile(r"(?i)\bне\b|\bnicht\b|\bkein\w{0,2}\b|\bpas\b|\bnão\b|ません|않|못|[?？¿]|\bwird\b|\bбудет\b|\bva\b")

LANGS = (("zh", ZH, ZH_DONE, ZH_ZERO, ZH_NEAR), ("th", TH, TH_DONE, TH_ZERO, TH_NEAR),
         ("es", ES, ES_DONE, ES_ZERO, ES_NEAR))
_MAIN = ("main", "master", "develop", "dev", "trunk", "staging", "production", "prod", "release")


def _branch(m: "re.Match") -> Optional[str]:
    b = next((g for g in m.groups() if g and not g.isdigit()), None)
    if not b:
        return None
    b = b.strip("`").rstrip(".,")
    if b.lower() in ("origin", "upstream", "remote", "github", "gitlab") or re.fullmatch(r"[0-9a-f]{7,40}", b):
        return None
    return b if (re.search(r"[/\-\d_]", b) or b in _MAIN) else None


def _pr(m: "re.Match") -> Optional[int]:
    n = next((g for g in m.groups() if g and g.isdigit()), None)
    return int(n) if n else None


def _broad(lang: str, piece: str) -> bool:
    """"All tests pass" (as wide as the suite) vs "the parser tests pass" (narrowed: never 🧢)."""
    if lang == "zh":
        return bool(re.search(r"所有|全部|整个|全量|都通过|均已?通过|全绿|^\W{0,3}(?:单元|集成)?测试", piece))
    if lang == "th":
        return bool(re.search(r"ทั้งหมด|ทุกตัว|ทุกอัน|ผ่านหมด|^\W{0,3}(?:การ)?(?:ทดสอบ|เทสต์|เทส|test)", piece))
    return bool(re.search(r"(?i)\btod[ao]s\b|^\W{0,3}(?:las pruebas|los tests?|la suite)\b", piece))


KANA_HANGUL_CYR_RE = re.compile(r"[\u3040-\u30ff\uac00-\ud7af\u0400-\u04ff]")


HAN_RE = re.compile(r"[\u4e00-\u9fff]")
KANA_RE = re.compile(r"[\u3040-\u30ff]")


def _languages(text: str) -> List[str]:
    """The checked languages a piece may be in (zh, th, es); "other" if it is in a script or language with no
    checker yet (Japanese kana, Korean, Cyrillic, German, French, Portuguese). Empty for plain English."""
    out = []
    if HAN_RE.search(text) and not KANA_RE.search(text):
        out.append("zh")  # Japanese also writes kanji: with kana in the piece, it isn't read as Chinese
    if THAI_RE.search(text):
        out.append("th")
    if _es_hint(text):
        out.append("es")
    if KANA_HANGUL_CYR_RE.search(text) or _other_hint(text):
        out.append("other")
    return out


def foreign_claims(clause: str) -> List[Dict[str, Any]]:
    """Claims in a clause written in Chinese, Thai or Spanish (or an `unchecked` completion phrase in another
    language). English clauses return [] after one cheap scan."""
    if not clause or not (NON_LATIN_RE.search(clause) or _es_hint(clause) or _other_hint(clause)):
        return []
    out: List[Dict[str, Any]] = []
    for pm in PIECE_RE.finditer(clause[:4000]):
        piece = pm.group(0).strip()
        if not piece:
            continue
        langs = _languages(piece)
        found = done_in = None
        for code, pats, done, zero, near in LANGS:
            if code not in langs:
                continue
            plain = zero.sub(" ", piece)
            if near.search(plain):
                found = found or False
                continue  # negated, future, conditional, hedged or a question: a near-miss, not a claim
            for kind, rx in pats.items():
                m = rx.search(plain)
                if not m:
                    continue
                c: Dict[str, Any] = {"kind": kind, "lang": code, "frag": piece[:200]}
                if kind == "tests":
                    c.update(passed=None, failed=None, total=None, all_pass=True, fails=False, count_only=False,
                             scoped=not _broad(code, plain))
                elif kind == "pushed":
                    c["branch"] = _branch(m)
                elif kind == "merged":
                    c.update(pr=_pr(m), git_merge=False)
                out.append(c)
                found = True
            if not found and not done_in and done.search(plain):
                done_in = code
        if found:
            continue
        if done_in:
            out.append({"kind": "unchecked", "lang": done_in, "frag": piece[:200]})
        elif found is None and "other" in langs and OTHER_DONE.search(piece) and not OTHER_NEAR.search(piece):
            out.append({"kind": "unchecked", "lang": "other", "frag": piece[:200]})
    return out
