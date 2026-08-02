const labels: Record<string, string> = {
  CREATED: "已受理",
  RUNNING: "处理中",
  WAITING_USER: "待补充信息",
  WAITING_APPROVAL: "等待审批",
  MANUAL_REVIEW: "人工核查",
  COMPLETED: "已完成",
  REJECTED: "未通过",
  FAILED: "处理失败",
  PENDING: "待审批",
  APPROVED: "已批准",
  ESCALATED: "已升级",
  RESOLVED: "已解决",
  UNRESOLVABLE: "无法解决",
  DELIVERED: "已签收"
};

export function StatusPill({ status, label }: { status: string; label?: string }) {
  return (
    <span className={"status status--" + status.toLowerCase()}>
      <i aria-hidden="true" />
      {label ?? labels[status] ?? status}
    </span>
  );
}
