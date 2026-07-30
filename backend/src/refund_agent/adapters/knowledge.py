from datetime import UTC, datetime

import jieba
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from refund_agent.models import KnowledgeDocument


def search_knowledge(db: Session, query: str, limit: int = 3) -> list[KnowledgeDocument]:
    tokens = [token.strip() for token in jieba.cut(query) if token.strip()]
    conditions = [KnowledgeDocument.search_tokens.contains(token) for token in tokens]
    if not conditions:
        return []
    now = datetime.now(UTC)
    statement = (
        select(KnowledgeDocument)
        .where(or_(*conditions))
        .where(KnowledgeDocument.effective_from <= now)
        .where(
            or_(
                KnowledgeDocument.effective_to.is_(None),
                KnowledgeDocument.effective_to > now,
            )
        )
        .limit(limit)
    )
    return list(db.scalars(statement))
