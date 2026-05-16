"""Load the 7 synthetic CSVs and produce per-account context bundles.

This is the "memory / context retrieval" stage from the Token Math Sheet.
In a production system this would be a vector search or DB query; here we
filter the in-memory DataFrames. We still count tokens of the assembled
context because that's what the LLM stages will pay for.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

DATA_DIR = Path(__file__).parent.parent / "data"


class CSData:
    def __init__(self):
        self.accounts = pd.read_csv(DATA_DIR / "accounts.csv")
        self.usage = pd.read_csv(DATA_DIR / "usage_events.csv")
        self.tickets = pd.read_csv(DATA_DIR / "support_tickets.csv")
        self.calls = pd.read_csv(DATA_DIR / "call_notes.csv")
        self.checkins = pd.read_csv(DATA_DIR / "scheduled_checkins.csv")
        self.outputs = pd.read_csv(DATA_DIR / "junior_outputs.csv")
        self.quality_standards = pd.read_csv(DATA_DIR / "quality_standards.csv")

    def account_context(self, account_id: str, *, include_call_notes=True,
                        include_tickets=True, include_usage=True) -> str:
        """Build a compact text context for a single account."""
        acc_row = self.accounts[self.accounts.account_id == account_id]
        if acc_row.empty:
            return f"Unknown account: {account_id}"
        a = acc_row.iloc[0]
        lines = [
            f"ACCOUNT: {a.account_id} ({a.account_name})",
            f"Segment: {a.segment} | Contract value: ${a.contract_value:,} | Renewal: {a.renewal_date}",
            f"CSM: {a.csm_owner}",
            f"Health score: {a.current_health_score} (was {a.previous_health_score}, trend: {a.product_usage_trend})",
            f"Support tickets last 30d: {a.support_ticket_count_30d} | NPS: {a.nps_score} | Expansion signal: {a.expansion_signal}",
            f"Last contact: {a.last_contact_date}",
            f"Notes: {a.notes}",
        ]
        if include_usage:
            u = self.usage[self.usage.account_id == account_id].sort_values("event_date")
            if not u.empty:
                lines.append("\nRECENT USAGE:")
                for _, r in u.iterrows():
                    lines.append(
                        f"  {r.event_date}: {r.active_users} active, "
                        f"{r.key_feature_users} power-users, trend={r.usage_trend}"
                    )
        if include_tickets:
            t = self.tickets[self.tickets.account_id == account_id]
            if not t.empty:
                lines.append("\nOPEN TICKETS:")
                for _, r in t.iterrows():
                    lines.append(
                        f"  [{r.ticket_id}] {r.date_received} sev={r.severity} "
                        f"sentiment={r.customer_sentiment} status={r.current_status}"
                    )
                    lines.append(f"    issue: {r.issue_summary}")
                    lines.append(f"    note: {r.frontline_notes}")
        if include_call_notes:
            c = self.calls[self.calls.account_id == account_id]
            if not c.empty:
                lines.append("\nRECENT CALL NOTES:")
                for _, r in c.iterrows():
                    lines.append(f"  {r.call_date} | {r.summary}")
                    lines.append(f"    goal: {r.customer_goal}")
                    lines.append(f"    risk: {r.risk_or_blocker}")
                    lines.append(f"    follow-up: {r.follow_up_items}")
        return "\n".join(lines)

    def ticket_context(self, ticket_id: str) -> str:
        t = self.tickets[self.tickets.ticket_id == ticket_id]
        if t.empty:
            return f"Unknown ticket: {ticket_id}"
        r = t.iloc[0]
        ticket_text = (
            f"TICKET: {r.ticket_id}\n"
            f"Account: {r.account_id}\n"
            f"Received: {r.date_received}\n"
            f"Severity: {r.severity}\n"
            f"Customer sentiment: {r.customer_sentiment}\n"
            f"Issue: {r.issue_summary}\n"
            f"Frontline notes: {r.frontline_notes}\n"
            f"Status: {r.current_status}\n\n"
            f"ACCOUNT CONTEXT:\n{self.account_context(r.account_id, include_call_notes=True, include_tickets=False, include_usage=True)}"
        )
        return ticket_text

    def checkin_context(self, checkin_id: str) -> str:
        c = self.checkins[self.checkins.checkin_id == checkin_id]
        if c.empty:
            return f"Unknown check-in: {checkin_id}"
        r = c.iloc[0]
        return (
            f"CHECK-IN: {r.checkin_id}\n"
            f"Account: {r.account_id}\n"
            f"Scheduled: {r.scheduled_date}\n"
            f"Type: {r.checkin_type}\n"
            f"Priority: {r.priority}\n"
            f"Topics to cover: {r.topics_to_cover}\n\n"
            f"ACCOUNT CONTEXT:\n{self.account_context(r.account_id)}"
        )

    def output_context(self, output_id: str) -> tuple[str, str, str]:
        o = self.outputs[self.outputs.output_id == output_id]
        if o.empty:
            raise ValueError(f"Unknown output: {output_id}")
        r = o.iloc[0]
        std_ids = [s.strip() for s in r.quality_standard_ids.split(";")]
        std_rows = self.quality_standards[self.quality_standards.standard_id.isin(std_ids)]
        standards_text = "\n".join(
            f"  {s.standard_id} - {s.standard_name}: {s.description}"
            for _, s in std_rows.iterrows()
        )
        account_ctx = self.account_context(
            r.account_id, include_call_notes=True, include_tickets=True, include_usage=False
        )
        draft_text = (
            f"OUTPUT: {r.output_id}\n"
            f"Type: {r.output_type}\n"
            f"Intended customer action: {r.intended_customer_action}\n"
            f"Quality standards to check: {', '.join(std_ids)}\n\n"
            f"DRAFT TEXT:\n{r.draft_text}\n\n"
            f"APPLICABLE STANDARDS:\n{standards_text}\n\n"
            f"ACCOUNT CONTEXT:\n{account_ctx}"
        )
        return draft_text, r.draft_text, standards_text
