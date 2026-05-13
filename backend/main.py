from datetime import datetime
from typing import List

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import SessionLocal, Base, engine
from models import Watchlist, EmailLog

app = FastAPI()

# Create tables
Base.metadata.create_all(bind=engine)

# CORS for extension
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Pydantic models ----------

class EmailIn(BaseModel):
    sender: str
    body: str
    subject: str | None = ""


class EmailOut(BaseModel):
    category: str
    priority: str
    summary: str

class EmailLogOut(BaseModel):
    id: int
    sender: str
    body: str
    category: str
    priority: str
    created_at: datetime

    

class EmailOut(BaseModel):
    category: str
    priority: str
    summary: str
    is_spam: bool
    is_phishing: bool
    is_subscription: bool
    has_hidden_fees: bool

    class Config:
        from_attributes = True  # Pydantic v2


# ---------- DB session dependency ----------

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------- Routes ----------

@app.get("/ping")
def ping():
    return {"status": "ok"}

@app.post("/analyze", response_model=EmailOut)
def analyze_email(payload: EmailIn, db: Session = Depends(get_db)):
    sender = payload.sender
    body = payload.body
    subject = payload.subject or ""

    # 1) Watchlist check (override category/priority if found)
    wl = db.query(Watchlist).filter(Watchlist.email == sender).first()

    # Rule-based analysis
    auto_category = detect_category(sender, subject, body)
    auto_priority = classify_priority(sender, subject, body)
    is_spam, is_phishing = detect_spam_and_phishing(sender, subject, body)
    is_subscription, subscription_type, has_hidden_fees = detect_subscription_and_fees(
        sender, subject, body
    )

    # If sender in watchlist, force category + High priority
    if wl:
        category = wl.category or auto_category
        priority = "High"
    else:
        category = auto_category
        priority = auto_priority

    summary = f"Email from {sender} categorized as {category}, priority {priority}."

    # 2) Save log into database (keep schema simple for now)
    log = EmailLog(
        sender=sender,
        body=body,
        category=category,
        priority=priority,
        # Agar EmailLog model me ye fields add karna chaho to uncomment karo:
        # is_spam=is_spam,
        # is_phishing=is_phishing,
        # is_subscription=is_subscription,
        # has_hidden_fees=has_hidden_fees,
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    # 3) Return full analysis
    return EmailOut(
        category=category,
        priority=priority,
        summary=summary,
        is_spam=is_spam,
        is_phishing=is_phishing,
        is_subscription=is_subscription,
        has_hidden_fees=has_hidden_fees,
    )


@app.get("/list_emails", response_model=List[EmailLogOut])
def list_emails(limit: int = 20, db: Session = Depends(get_db)):
    logs = (
        db.query(EmailLog)
        .order_by(EmailLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return logs

# ---- Simple rule-based helpers ----

def classify_priority(sender: str, subject: str, body: str) -> str:
    text = f"{subject} {body}".lower()
    sender_lower = sender.lower()
    score = 0

    # ... existing scoring rules ...

    # Social senders or social-like content => slightly lower
    social_domains = ["linkedin.com", "facebookmail.com", "instagram.com", "twitter.com", "x.com"]
    social_keywords = ["liked your post", "commented on", "followed you", "connection request"]
    if any(d in sender_lower for d in social_domains) or any(k in text for k in social_keywords):
        score -= 1

    if score >= 3:
        return "High"
    elif score <= -1:
        return "Low"
    else:
        return "Normal"


def detect_category(sender: str, subject: str, body: str) -> str:
    text = f"{subject} {body}".lower()
    sender_lower = sender.lower()

    # 1) Social / network notifications
    social_domains = ["linkedin.com", "facebookmail.com", "instagram.com", "twitter.com", "x.com"]
    social_keywords = [
        "liked your post",
        "commented on",
        "mentioned you",
        "connection request",
        "followed you",
        "new follower",
        "people you may know",
        "suggested for you"
    ]
    if any(d in sender_lower for d in social_domains) or any(k in text for k in social_keywords):
        return "Social"

    # 2) Work
    work_keywords = ["meeting", "project", "deadline", "client", "task", "assignment"]
    if any(w in text for w in work_keywords):
        return "Work"

    # 3) Transactions
    transaction_keywords = ["invoice", "payment", "transaction", "receipt", "order", "purchase"]
    if any(w in text for w in transaction_keywords):
        return "Transactions"

    # 4) Notifications
    notification_keywords = ["notification", "alert", "login", "security", "otp", "verification code"]
    if any(w in text for w in notification_keywords):
        return "Notifications"

    # 5) Promotions
    promo_keywords = [
        "sale", "discount", "offer", "deal", "coupon",
        "limited time", "hiring for", "apply now", "followers", "suggested for you"
    ]
    if any(w in text for w in promo_keywords):
        return "Promotions"

    # 6) Personal
    personal_keywords = ["dear", "hi ", "hello", "regards", "thank you"]
    if any(w in text for w in personal_keywords):
        return "Personal"

    return "General"


def detect_spam_and_phishing(sender: str, subject: str, body: str) -> tuple[bool, bool]:
    text = f"{subject} {body}".lower()
    sender_lower = sender.lower()

    is_spam = False
    is_phishing = False

    spam_keywords = ["lottery", "win money", "prize", "free gift", "congratulations"]
    if any(w in text for w in spam_keywords):
        is_spam = True

    phishing_keywords = [
        "verify your account",
        "update your account",
        "suspend your account",
        "login to continue",
        "confirm your password",
        "confirm your identity",
        "account will be closed",
    ]
    if any(w in text for w in phishing_keywords):
        is_phishing = True

    sensitive_keywords = ["password", "otp", "pin", "cvv", "card number", "bank account"]
    if any(w in text for w in sensitive_keywords) and "http" in text:
        is_phishing = True

    suspicious_domains = ["support-secure", "security-alert", "billing-secure"]
    if any(dom in sender_lower for dom in suspicious_domains):
        is_phishing = True

    return is_spam, is_phishing


def detect_subscription_and_fees(sender: str, subject: str, body: str) -> tuple[bool, str, bool]:
    text = f"{subject} {body}".lower()
    sender_lower = sender.lower()

    is_subscription = False
    subscription_type = "Unknown"
    has_hidden_fees = False

    subscription_keywords = [
        "subscription",
        "auto-renew",
        "billing cycle",
        "plan will renew",
        "renewal",
        "trial period",
        "your plan will be renewed",
    ]
    if any(w in text for w in subscription_keywords):
        is_subscription = True

    streaming_domains = ["netflix", "primevideo", "spotify", "youtube", "hotstar"]
    if any(d in sender_lower for d in streaming_domains):
        is_subscription = True
        subscription_type = "Streaming"

    edu_domains = ["coursera", "udemy", "byjus", "unacademy", "thinkific"]
    if any(d in sender_lower for d in edu_domains):
        is_subscription = True
        subscription_type = "Education"

    hidden_fee_phrases = [
        "after the trial period you will be charged",
        "introductory price",
        "standard price",
        "additional charges may apply",
        "taxes extra",
        "terms and conditions apply",
    ]
    if any(p in text for p in hidden_fee_phrases):
        has_hidden_fees = True
        is_subscription = True

    return is_subscription, subscription_type, has_hidden_fees
