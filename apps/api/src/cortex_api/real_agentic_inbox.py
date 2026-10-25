"""
Cortex — agentic-inbox Engine

Self-hosted email client with AI agent coordination on Cloudflare Workers.
AI agent email triage, async workflow, message classification, and agent
email automation.

Tests: tests/test_real_batch4a.py
"""

from __future__ import annotations

import hashlib
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EmailMessage:
    """A single email message."""
    message_id: str
    sender: str
    recipient: str
    subject: str = ""
    body: str = ""
    timestamp: float = 0.0
    is_read: bool = False
    is_starred: bool = False
    labels: list[str] = field(default_factory=list)
    thread_id: str = ""

    @staticmethod
    def create_message(sender: str, recipient: str, subject: str, body: str) -> EmailMessage:
        mid = hashlib.md5(f"{sender}:{subject}:{time.time()}".encode()).hexdigest()[:16]
        return EmailMessage(
            message_id=f"msg-{mid}",
            sender=sender,
            recipient=recipient,
            subject=subject,
            body=body,
            timestamp=time.time(),
            thread_id=f"thread-{hashlib.md5(subject.encode()).hexdigest()[:12]}",
        )

    @property
    def is_thread_start(self) -> bool:
        return not self.thread_id.startswith("re:")

    @property
    def word_count(self) -> int:
        return len(self.body.split())

    @property
    def priority_score(self) -> float:
        score = 0.0
        urgent_words = ["urgent", "asap", "important", "critical", "emergency", "deadline"]
        for word in urgent_words:
            if word.lower() in self.subject.lower() or word.lower() in self.body.lower():
                score += 0.2
        if not self.is_read:
            score += 0.1
        if len(self.subject) > 0:
            score += 0.05
        return score

    def mark_read(self) -> None:
        self.is_read = True

    def mark_unread(self) -> None:
        self.is_read = False

    def add_label(self, label: str) -> None:
        if label not in self.labels:
            self.labels.append(label)

    def remove_label(self, label: str) -> None:
        if label in self.labels:
            self.labels.remove(label)


@dataclass
class EmailThread:
    """Email thread."""
    thread_id: str
    subject: str
    messages: list[EmailMessage] = field(default_factory=list)

    @staticmethod
    def create_thread(subject: str) -> EmailThread:
        tid = hashlib.md5(subject.encode()).hexdigest()[:12]
        return EmailThread(thread_id=f"thread-{tid}", subject=subject)

    def add_message(self, message: EmailMessage) -> None:
        self.messages.append(message)

    @property
    def message_count(self) -> int:
        return len(self.messages)

    @property
    def last_activity(self) -> float:
        if not self.messages:
            return 0.0
        return max(m.timestamp for m in self.messages)

    @property
    def participants(self) -> set[str]:
        participants = set()
        for m in self.messages:
            participants.add(m.sender)
            participants.add(m.recipient)
        return participants

    @property
    def is_unread(self) -> bool:
        return any(not m.is_read for m in self.messages)

    @property
    def total_words(self) -> int:
        return sum(m.word_count for m in self.messages)


@dataclass
class AIEmailAgent:
    """AI agent for email coordination."""
    @staticmethod
    def classify_email(message: EmailMessage) -> str:
        subject_lower = message.subject.lower()
        body_lower = message.body.lower()
        if any(w in subject_lower for w in ["meeting", "calendar", "schedule"]):
            return "meeting"
        elif any(w in subject_lower for w in ["invoice", "payment", "bill"]):
            return "finance"
        elif any(w in subject_lower for w in ["support", "help", "issue", "bug"]):
            return "support"
        elif any(w in subject_lower for w in ["promotion", "sale", "offer", "discount"]):
            return "promotion"
        elif any(w in subject_lower for w in ["newsletter", "update", "digest"]):
            return "newsletter"
        elif any(w in subject_lower for w in ["job", "hiring", "resume"]):
            return "recruiting"
        else:
            return "other"

    @staticmethod
    def extract_action_items(body: str) -> list[str]:
        action_patterns = [
            r"(?:please|kindly|need to|must|should|let's|lets)\s+([^.]+)",
            r"action:\s*([^\n]+)",
            r"todo:\s*([^\n]+)",
            r"follow[- ]up:\s*([^\n]+)",
        ]
        items = []
        for pattern in action_patterns:
            matches = re.findall(pattern, body, re.IGNORECASE)
            for match in matches:
                match = match.strip()
                if len(match) > 5:
                    items.append(match[:200])
        return items

    @staticmethod
    def summarize_email(message: EmailMessage) -> str:
        sentences = [s.strip() for s in re.split(r'[.!?]', message.body) if s.strip()]
        if not sentences:
            return message.subject
        if len(sentences) <= 3:
            return " ".join(sentences)
        return sentences[0] + ". " + sentences[1]

    @staticmethod
    def detect_sentiment(text: str) -> str:
        text_lower = text.lower()
        positive_words = ["great", "good", "excellent", "amazing", "thanks", "appreciate", "love", "wonderful", "fantastic"]
        negative_words = ["bad", "terrible", "awful", "wrong", "broken", "issue", "problem", "error", "fail", "hate"]
        pos = sum(1 for w in positive_words if w in text_lower)
        neg = sum(1 for w in negative_words if w in text_lower)
        if pos > neg:
            return "positive"
        elif neg > pos:
            return "negative"
        else:
            return "neutral"

    @staticmethod
    def extract_entities(text: str) -> dict[str, list[str]]:
        urls = re.findall(r'https?://\S+', text)
        emails = re.findall(r'\b[\w.+-]+@[\w-]+\.[\w.-]+\b', text)
        dates = re.findall(r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b', text)
        times = re.findall(r'\b\d{1,2}:\d{2}\s*(?:am|pm|AM|PM)?\b', text)
        return {"urls": urls, "emails": emails, "dates": dates, "times": times}

    @staticmethod
    def draft_reply(message: EmailMessage, tone: str = "professional") -> str:
        if tone == "casual":
            greeting = "Hey!"
            closing = "Best"
        else:
            greeting = "Dear [Name],"
            closing = "Sincerely"
        reply = f"{greeting}\n\nThank you for your email regarding \"{message.subject}\".\n\nI have reviewed your message and will get back to you shortly.\n\n{closing}"
        return reply

    @staticmethod
    def detect_spam(message: EmailMessage) -> bool:
        spam_words = ["free", "winner", "prize", "click here", "act now", "limited time", "guaranteed", "no obligation"]
        text = (message.subject + " " + message.body).lower()
        spam_count = sum(1 for w in spam_words if w in text)
        return spam_count >= 2

    @staticmethod
    def auto_label(message: EmailMessage) -> list[str]:
        category = AIEmailAgent.classify_email(message)
        labels = [category]
        if message.priority_score > 0.4:
            labels.append("high_priority")
        if AIEmailAgent.detect_spam(message):
            labels.append("spam")
        return labels


@dataclass
class InboxState:
    """Inbox state manager."""
    messages: list[EmailMessage] = field(default_factory=list)
    threads: dict[str, EmailThread] = field(default_factory=dict)
    labels: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))

    def add_message(self, message: EmailMessage) -> None:
        self.messages.append(message)
        if message.thread_id not in self.threads:
            self.threads[message.thread_id] = EmailThread(
                thread_id=message.thread_id,
                subject=message.subject,
            )
        self.threads[message.thread_id].add_message(message)
        for label in message.labels:
            self.labels[label].append(message.message_id)

    def get_unread(self) -> list[EmailMessage]:
        return [m for m in self.messages if not m.is_read]

    def get_by_label(self, label: str) -> list[EmailMessage]:
        msg_ids = self.labels.get(label, [])
        return [m for m in self.messages if m.message_id in msg_ids]

    def get_by_sender(self, sender: str) -> list[EmailMessage]:
        return [m for m in self.messages if sender in m.sender]

    def search(self, query: str) -> list[EmailMessage]:
        query_lower = query.lower()
        return [
            m for m in self.messages
            if query_lower in m.subject.lower() or query_lower in m.body.lower()
        ]

    @property
    def unread_count(self) -> int:
        return len(self.get_unread())

    @property
    def message_count(self) -> int:
        return len(self.messages)

    @property
    def thread_count(self) -> int:
        return len(self.threads)

    @property
    def label_count(self) -> int:
        return len(self.labels)

    def thread_for(self, message: EmailMessage) -> EmailThread | None:
        return self.threads.get(message.thread_id)


@dataclass
class AsyncEmailWorker:
    """Async email worker for Cloudflare Workers style processing."""
    @staticmethod
    def process_inbox(inbox: InboxState, agent: AIEmailAgent) -> dict[str, Any]:
        classified = []
        action_items = []
        spam_count = 0
        for message in inbox.messages:
            if not message.is_read:
                category = agent.classify_email(message)
                message.add_label(category)
                classified.append({
                    "message_id": message.message_id,
                    "category": category,
                    "priority": message.priority_score,
                })
                items = agent.extract_action_items(message.body)
                action_items.extend(items)
                if agent.detect_spam(message):
                    spam_count += 1
                    message.add_label("spam")
        return {
            "processed": inbox.message_count,
            "classified": len(classified),
            "action_items": len(action_items),
            "spam_detected": spam_count,
        }

    @staticmethod
    def triage_messages(inbox: InboxState) -> dict[str, list[str]]:
        categories = defaultdict(list)
        for message in inbox.get_unread():
            category = AIEmailAgent.classify_email(message)
            categories[category].append(message.message_id)
        return dict(categories)

    @staticmethod
    def generate_digest(inbox: InboxState) -> dict[str, Any]:
        unread = inbox.get_unread()
        digest = {
            "unread_count": len(unread),
            "top_senders": [],
            "categories": defaultdict(int),
            "urgent_messages": [],
        }
        sender_counts = defaultdict(int)
        for msg in unread:
            sender_counts[msg.sender] += 1
            category = AIEmailAgent.classify_email(msg)
            digest["categories"][category] += 1
            if msg.priority_score > 0.4:
                digest["urgent_messages"].append({
                    "subject": msg.subject,
                    "sender": msg.sender,
                    "priority": msg.priority_score,
                })
        top_senders = sorted(sender_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        digest["top_senders"] = [{"sender": s, "count": c} for s, c in top_senders]
        return digest

    @staticmethod
    def scheduled_email_check(last_check: float, now: float, interval: float = 300.0) -> bool:
        return (now - last_check) >= interval

    @staticmethod
    def batch_process(messages: list[EmailMessage], agent: AIEmailAgent) -> list[dict]:
        results = []
        for msg in messages:
            results.append({
                "message_id": msg.message_id,
                "category": agent.classify_email(msg),
                "action_items": agent.extract_action_items(msg.body),
                "sentiment": agent.detect_sentiment(msg.body),
                "spam": agent.detect_spam(msg),
            })
        return results


@dataclass
class AgentCoordinator:
    """Agent coordination for email workflows."""
    @staticmethod
    def route_message(message: EmailMessage) -> str:
        category = AIEmailAgent.classify_email(message)
        if category == "support":
            return "support_agent"
        elif category == "finance":
            return "finance_agent"
        elif category == "meeting":
            return "calendar_agent"
        elif category == "recruiting":
            return "hr_agent"
        elif category == "promotion":
            return "marketing_agent"
        else:
            return "general_agent"

    @staticmethod
    def assign_to_agent(message: EmailMessage, agent_capabilities: dict[str, list[str]]) -> str | None:
        category = AIEmailAgent.classify_email(message)
        for agent_name, capabilities in agent_capabilities.items():
            if category in capabilities:
                return agent_name
        return None

    @staticmethod
    def coordination_plan(messages: list[EmailMessage]) -> dict[str, list[str]]:
        plan = defaultdict(list)
        for msg in messages:
            category = AIEmailAgent.classify_email(msg)
            agent = AgentCoordinator.route_message(msg)
            plan[agent].append(msg.message_id)
        return dict(plan)

    @staticmethod
    def escalation_needed(message: EmailMessage) -> bool:
        if message.priority_score > 0.6:
            return True
        if AIEmailAgent.detect_spam(message):
            return True
        if message.word_count > 500:
            return True
        return False

    @staticmethod
    def response_time_metrics(messages: list[EmailMessage]) -> dict[str, Any]:
        if not messages:
            return {"avg_response_time": 0.0, "fastest": 0.0, "slowest": 0.0}
        response_times = []
        for msg in messages:
            if msg.timestamp > 0:
                response_times.append(msg.timestamp)
        if not response_times:
            return {"avg_response_time": 0.0, "fastest": 0.0, "slowest": 0.0}
        return {
            "avg_response_time": sum(response_times) / len(response_times),
            "fastest": min(response_times),
            "slowest": max(response_times),
        }

    @staticmethod
    def agent_workload_balance(messages: list[EmailMessage], num_agents: int) -> dict[str, int]:
        plan = AgentCoordinator.coordination_plan(messages)
        agent_names = list(plan.keys()) if plan else []
        if not agent_names:
            agent_names = [f"agent_{i}" for i in range(num_agents)]
        workload = defaultdict(int)
        for msg_id_list in plan.values():
            workload[msg_id_list[0] if msg_id_list else "unassigned"] += len(msg_id_list)
        for name in agent_names:
            if name not in workload:
                workload[name] = 0
        return dict(workload)
