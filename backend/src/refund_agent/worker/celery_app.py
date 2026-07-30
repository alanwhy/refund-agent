from celery import Celery

from refund_agent.config import get_settings

settings = get_settings()
celery_app = Celery("refund_agent", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    beat_schedule={
        "escalate-expired-approvals": {
            "task": "refund_agent.escalate_expired_approvals",
            "schedule": 60.0,
        }
    },
)
celery_app.autodiscover_tasks(["refund_agent.worker"])
