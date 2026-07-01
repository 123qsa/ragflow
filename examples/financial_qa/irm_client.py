#
#  Copyright 2025 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  ...
#
"""
互动易 & 上证e互动 投资者问答客户端。

使用 akshare 获取沪深两市投资者与上市公司的互动问答。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class IrmQuestion:
    stock_code: str
    stock_name: str
    question: str
    answer: str
    question_time: str
    answer_time: str
    questioner: str = ""
    source: str = "szse"


class IrmClient:
    """互动易 & 上证e互动 — 统一客户端"""

    def __init__(self):
        pass

    def fetch_questions(self, stock_code: str) -> List[IrmQuestion]:
        """获取投资者互动问答。"""
        questions: List[IrmQuestion] = []

        # 深市：互动易
        try:
            import akshare as ak
            df = ak.stock_irm_cninfo(symbol=stock_code)
            if df is not None and len(df) > 0:
                for _, row in df.iterrows():
                    answer = str(row.get("回答内容", ""))
                    if answer == "nan" or not answer.strip():
                        answer = ""
                    questions.append(IrmQuestion(
                        stock_code=stock_code,
                        stock_name=str(row.get("公司简称", stock_code)),
                        question=str(row.get("问题", "")).strip(),
                        answer=answer.strip(),
                        question_time=str(row.get("提问时间", "")),
                        answer_time=str(row.get("更新时间", "")),
                        questioner=str(row.get("提问者", "")),
                        source="szse",
                    ))
                print(f"[IRM] {stock_code} 互动易: {len(questions)} 条")
        except Exception as e:
            print(f"[IRM] 互动易失败 {stock_code}: {e}")

        return questions

    def to_document_text(self, questions: List[IrmQuestion]) -> Optional[str]:
        """将问答列表转换为知识库文档文本。"""
        if not questions:
            return None

        source_name = "互动易" if questions[0].source == "szse" else "上证e互动"
        name = questions[0].stock_name or questions[0].stock_code
        code = questions[0].stock_code

        lines = [
            f"# {name}（{code}）{source_name}投资者问答",
            f"# 共 {len(questions)} 条问答",
            f"# 更新时间：{datetime.now().strftime('%Y-%m-%d')}",
            "",
        ]

        for i, q in enumerate(questions, 1):
            lines.append(f"## 问答 {i}")
            lines.append(f"- 提问时间：{q.question_time}")
            lines.append(f"- 回答时间：{q.answer_time}")
            if q.questioner:
                lines.append(f"- 提问人：{q.questioner}")
            lines.append("")
            lines.append(f"**问：**{q.question}")
            lines.append("")
            lines.append(f"**答：**{q.answer}")
            lines.append("")
            lines.append("---")
            lines.append("")

        return "\n".join(lines)
