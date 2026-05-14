from datetime import datetime
from pathlib import Path
from typing import List

import joblib
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


# ---------- ML classifier load (sklearn) ----------

CLASSIFIER = None


def load_email_classifier():
    global CLASSIFIER
    model_path = Path(__file__).parent / "email_classifier.pkl"
    if model_path.exists():
        CLASSIFIER = joblib.load(model_path)
        print("Loaded email_classifier.pkl")
    else:
        CLASSIFIER = None
        print("email_classifier.pkl not found, ML classifier disabled")


load_email_classifier()


# ---------- Pydantic models ----------

class EmailIn(BaseModel):
    sender: str
    body: str
    subject: str | None = ""

class EmailOut(BaseModel):
    category: str
    priority: str
    summary: str
    is_spam: bool
    is_phishing: bool
    is_subscription: bool
    has_hidden_fees: bool
    ml_label: str | None = None

class EmailLogOut(BaseModel):
    id: int
    sender: str
    body: str
    category: str
    priority: str
    ml_label: str | None = None
    created_at: datetime

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

    # Watchlist override
    wl = db.query(Watchlist).filter(Watchlist.email == sender).first()

    # Rule-based analysis
    auto_category = detect_category(sender, subject, body)
    auto_priority = classify_priority(sender, subject, body)
    is_spam_rule, is_phishing = detect_spam_and_phishing(sender, subject, body)
    is_subscription, subscription_type, has_hidden_fees = detect_subscription_and_fees(
        sender, subject, body
    )

    # ML classifier prediction (optional)
    ml_label = None
    if CLASSIFIER is not None:
        text_for_model = f"{subject} {body}"
        try:
            ml_label = CLASSIFIER.predict([text_for_model])[0]
        except Exception as e:
            print("Email classifier error:", e)

    # Use ML label to strengthen subscription/hidden-fee detection
    if ml_label == "subscription_hidden_fee":
        is_subscription = True
        has_hidden_fees = True

    # Final category/priority (watchlist has highest priority)
    if wl:
        category = wl.category or auto_category
        priority = "High"
    else:
        category = auto_category
        priority = auto_priority

    summary = f"Email from {sender} categorized as {category}, priority {priority}."

    # Save log
    log = EmailLog(
        sender=sender,
        body=body,
        category=category,
        priority=priority,
        ml_label=ml_label,
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    return EmailOut(
        category=category,
        priority=priority,
        summary=summary,
        is_spam=is_spam_rule,
        is_phishing=is_phishing,
        is_subscription=is_subscription,
        has_hidden_fees=has_hidden_fees,
        ml_label=ml_label,
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

    urgent_keywords = ["urgent", "immediately", "asap", "action required", "last chance"]
    for word in urgent_keywords:
        if word in text:
            score += 2

    deadline_keywords = ["today", "tomorrow", "within 24 hours", "due date", "deadline"]
    for word in deadline_keywords:
        if word in text:
            score += 1

    important_keywords = ["payment", "invoice", "transaction", "security alert", "login attempt"]
    for word in important_keywords:
        if word in text:
            score += 2

    promo_keywords = ["sale", "discount", "offer", "newsletter", "promotion", "deal"]
    for word in promo_keywords:
        if word in text:
            score -= 1

    # Social / low‑importance senders
    social_domains = ["linkedin.com", "facebookmail.com", "instagram.com", "twitter.com", "x.com"]
    social_keywords = ["liked your post", "commented on", "followed you", "connection request"]
    if any(d in sender_lower for d in social_domains) or any(k in text for k in social_keywords):
        score -= 1

    # Service / policy notifications from Google/YouTube
    service_domains = ["accounts.google.com", "youtube.com", "google.com"]
    policy_keywords = [
        "terms of service",
        "community guidelines",
        "privacy policy",
        "mandatory email service announcement",
    ]
    if any(d in sender_lower for d in service_domains) and any(k in text for k in policy_keywords):
        score += 1

    if score >= 3:
        return "High"
    elif score <= -1:
        return "Low"
    else:
        return "Normal"


def detect_category(sender: str, subject: str, body: str) -> str:
    text = f"{subject} {body}".lower()
    sender_lower = sender.lower()

    # Social / network notifications
    social_domains = ["linkedin.com", "facebookmail.com", "instagram.com", "twitter.com", "x.com"]
    social_keywords = [
        "liked your post",
        "commented on",
        "mentioned you",
        "connection request",
        "followed you",
        "new follower",
        "people you may know",
        "suggested for you",
    ]
    if any(d in sender_lower for d in social_domains) or any(k in text for k in social_keywords):
        return "Social"

    # Service / policy notifications (Google, YouTube, etc.)
    service_domains = ["accounts.google.com", "youtube.com", "google.com"]
    service_keywords = [
        "terms of service",
        "community guidelines",
        "privacy policy",
        "mandatory email service announcement",
        "security alert",
        "policy update",
    ]
    if any(d in sender_lower for d in service_domains) and any(k in text for k in service_keywords):
        return "Notifications"

    # Work
    work_keywords = ["meeting", "project", "deadline", "client", "task", "assignment"]
    if any(w in text for w in work_keywords):
        return "Work"

    # Transactions
    transaction_keywords = ["invoice", "payment", "transaction", "receipt", "order", "purchase"]
    if any(w in text for w in transaction_keywords):
        return "Transactions"

    # Notifications (general)
    notification_keywords = ["notification", "alert", "login", "security", "otp", "verification code"]
    if any(w in text for w in notification_keywords):
        return "Notifications"

    # Promotions
    promo_keywords = [
        "sale",
        "discount",
        "offer",
        "deal",
        "coupon",
        "limited time",
        "hiring for",
        "apply now",
        "followers",
        "suggested for you",
    ]
    if any(w in text for w in promo_keywords):
        return "Promotions"

    # Personal
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
