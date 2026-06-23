"""AI 共创讨论：开场注入『主题 + 素材库摘要』，之后维护多轮上下文（暂不逐轮检索）。"""
from app.services.llm import get_llm

SYSTEM_TEMPLATE = """你是一位写作共创助手，正在和用户围绕一个主题展开讨论，帮助他梳理问题、挖掘观点、发现角度，逐步明确文章的表达方向。

本次共创主题：{topic}

用户素材库中已有以下素材摘要（供你参考，可在讨论中引用其中的事实、案例与观点）：
{summaries}

请基于主题和这些素材，主动、有条理地推进讨论；多提出有启发性的角度和追问，不要泛泛而谈。"""


def build_system_prompt(topic: str, context: str) -> str:
    summaries = context.strip() if context and context.strip() else "（素材库暂无可用摘要）"
    return SYSTEM_TEMPLATE.format(topic=topic, summaries=summaries)


def opening_message(topic: str, context: str) -> str:
    """会话开场：让 AI 基于主题与素材抛出讨论起点。"""
    llm = get_llm()
    if not llm.enabled:
        lines = [
            f"（本地模式）我们围绕「{topic}」展开共创。我已读取你素材库中的摘要，建议可以从这些角度切入：",
            "1. 这个主题最想向读者传达的核心观点是什么？",
            "2. 哪些素材最能支撑你的观点，能否举一两个例子？",
            "3. 文章面向谁、希望达到什么效果？",
            "你先说说初步想法，我们一起把方向聊清楚。",
        ]
        return "\n".join(lines)
    messages = [
        {"role": "system", "content": build_system_prompt(topic, context)},
        {
            "role": "user",
            "content": "我们开始吧。请你先结合主题和素材，抛出几个值得讨论的角度或问题，引导我展开思考。",
        },
    ]
    try:
        return llm.chat_messages(messages).strip()
    except Exception:
        return f"我们围绕「{topic}」开始讨论吧，你最想表达的核心观点是什么？"


def reply(topic: str, context: str, history: list[dict]) -> str:
    """history 为按时间排序的 [{role, content}]（不含 system）。"""
    llm = get_llm()
    if not llm.enabled:
        last = next((m["content"] for m in reversed(history) if m["role"] == "user"), "")
        return (
            "（本地模式）你提到：" + (last[:60] + "…" if len(last) > 60 else last) + "\n"
            "可以再具体一点吗？比如它对应素材库里的哪个案例、想得出什么结论？配置大模型后这里会给出更有质量的共创回复。"
        )
    messages = [{"role": "system", "content": build_system_prompt(topic, context)}]
    messages += [{"role": m["role"], "content": m["content"]} for m in history]
    try:
        return llm.chat_messages(messages).strip()
    except Exception:
        return "抱歉，刚才的回复出了点问题，请再说一次或换个角度。"
