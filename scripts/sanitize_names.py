#!/usr/bin/env python3
"""保守版二次脱敏：只替换在"明确人物指代"语境里的中文人名。

策略：只匹配以下确定语境，不做开放式姓氏扫描，避免误伤业务词。
- 「用户XX」「受访者XX」「客户XX」「乘客XX」「小姐XX」「先生XX」
- 「（XXX）」「(XXX)」并且括号内是2-4个汉字、含百家姓首字
"""
import json
import re
from pathlib import Path

SAMPLE = Path("/Users/xuwenxiang/.qoderwork/skills/virtual_user_skill/data/sample_scenarios.json")
NARRATIVE = ['用户具体场景', '任务', '期待效果', '当前方案', '爽点', '痛点', '改进方向', '底层需求']
PLACEHOLDER = "[受访者]"

# 缩减版百家姓：只保留实际作为姓氏远多于普通词的字
SURNAMES = set("赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦许何吕施张孔曹严华魏陶姜戚谢邹喻窦章潘葛奚范彭郎鲁韦昌马苗方俞任袁柳鲍史唐费廉岑薛雷贺倪汤滕殷罗毕郝邬安傅皮卞齐康伍卜顾孟黄穆萧尹姚邵汪祁狄米贝臧伏戴谈宋茅庞熊纪舒屈项祝董梁杜阮蓝闵席季麻贾娄童颜郭梅盛林刁钟徐邱骆夏蔡田樊胡凌霍虞万柯管卢莫房简饶曾鞠丰巢蒯查竺权逯桓胥闻翟谭姬冉宰郦雍桑桂濮牛寿扈燕冀浦尚晏柴瞿阎慕茹艾容戈廖耿弘匡寇禄聂晁敖訾")

DOUBLE_SURNAMES = ["欧阳", "司马", "上官", "诸葛", "夏侯", "皇甫", "尉迟", "公孙", "万俟", "赫连", "宇文", "慕容", "长孙", "西门", "南宫", "东方"]

EXCLUDE_NAMES = {
    # 常见地名/产品/品牌词，含姓氏字但不是人名
    "韩国", "韩餐", "韩流", "韩文", "韩元", "韩剧", "周边", "周末", "周年", "金额", "金银", "金店", "金价",
    "黄金", "胡同", "胡椒", "万达", "范围", "梁山", "鲍鱼", "罗马", "罗盘", "路线", "马桶", "马上", "石头",
    "罗盘", "石材", "齐全", "齐心", "舒适", "黄页", "黄昏", "周岁", "周一", "周二", "周三", "周四", "周五",
    "周六", "周日", "周到", "万一", "万元", "万家", "万分", "夏天", "夏季", "蒋家", "蒋家", "唐朝", "宋代",
    "明朝", "清朝", "汉朝", "唐代", "汉子", "汉服", "汉语", "汉字", "国家", "国内", "国外", "国际", "马云",
    "鲁班", "罗辑", "成都", "颜值", "颜色", "高峰", "高速", "高铁", "高德", "魏晋", "梅花", "盛夏", "麻烦",
    "麻辣", "高潮", "蔡司", "邱比", "万圣", "万能", "桑拿", "丰富", "丰盛", "戴森", "胡萝", "戴尔", "胡萝卜",
    "杜拜", "马术", "马来", "马尔", "罗斯", "英国", "美国", "中国", "全国", "本国", "国旗",
}

# Person-context patterns
CONTEXT_PATTERNS = [
    re.compile(r'(?<=用户)[\u4e00-\u9fa5]{2,4}'),
    re.compile(r'(?<=受访者)[\u4e00-\u9fa5]{2,4}'),
    re.compile(r'(?<=客户)[\u4e00-\u9fa5]{2,4}'),
    re.compile(r'(?<=乘客)[\u4e00-\u9fa5]{2,4}'),
    re.compile(r'(?<=被访者)[\u4e00-\u9fa5]{2,4}'),
    re.compile(r'[\u4e00-\u9fa5]{2,4}(?=小姐)'),
    re.compile(r'[\u4e00-\u9fa5]{2,4}(?=先生)'),
    re.compile(r'[\u4e00-\u9fa5]{2,4}(?=女士)'),
]
# Bracket pattern: "（XXX）" or "(XXX)"
BRACKET = re.compile(r'[（(]([\u4e00-\u9fa5]{2,4})[）)]')


def is_likely_name(s):
    """返回 s 是否可能是真实姓名。"""
    if s in EXCLUDE_NAMES: return False
    if any(s.startswith(d) for d in DOUBLE_SURNAMES): return True
    return s[0] in SURNAMES


def sanitize_text(text):
    if not text: return text, []
    replaced = []
    new_text = text

    # Pattern 1: context-prefixed/suffixed names — replace whole match (incl context)
    for pat in CONTEXT_PATTERNS:
        # find all matches first to avoid moving offsets
        for m in list(pat.finditer(new_text)):
            cand = m.group()
            if is_likely_name(cand):
                replaced.append(cand)
        # do replacement once after collection, using sub with callback
        def repl(m):
            cand = m.group()
            return PLACEHOLDER if is_likely_name(cand) else cand
        new_text = pat.sub(repl, new_text)

    # Pattern 2: bracketed names — replace whole bracket including parens
    def bracket_repl(m):
        cand = m.group(1)
        if is_likely_name(cand):
            replaced.append(cand)
            return f'（{PLACEHOLDER}）'
        return m.group()
    new_text = BRACKET.sub(bracket_repl, new_text)

    return new_text, replaced


def main():
    data = json.loads(SAMPLE.read_text(encoding='utf-8'))
    all_replaced = []
    for r in data:
        for f in NARRATIVE:
            if not r.get(f): continue
            new_text, repl = sanitize_text(r[f])
            if repl:
                r[f] = new_text
                all_replaced.extend([(r['序号'], f, n) for n in repl])

    print(f'Replaced {len(all_replaced)} occurrences:')
    for sn, fld, name in all_replaced:
        print(f'  #{sn} {fld}: {name}')

    SAMPLE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'\n✓ Sanitized sample saved ({SAMPLE.stat().st_size/1024:.1f} KB)')


if __name__ == "__main__":
    main()
