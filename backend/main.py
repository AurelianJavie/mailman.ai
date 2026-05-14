from datetime import datetime
from pathlib import Path
from typing import List, Optional
import re

import joblib
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import SessionLocal, Base, engine
from models import Watchlist, EmailLog

app = FastAPI()

Base.metadata.create_all(bind=engine)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── ML classifier load ───────────────────────────────────────────

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


# ─── Pydantic models ──────────────────────────────────────────────

class EmailIn(BaseModel):
    id: Optional[str] = None
    sender: str
    body: str
    subject: Optional[str] = ""
    snippet: Optional[str] = ""

class EmailOut(BaseModel):
    category: str
    priority: str
    summary: str
    is_spam: bool
    is_phishing: bool
    is_subscription: bool
    has_hidden_fees: bool
    otp_category: str        # "otp" | "travel" | "work" | "normal" | "spam" | "promo"
    ml_label: Optional[str] = None

class EmailLogOut(BaseModel):
    id: int
    sender: str
    body: str
    category: str
    priority: str
    ml_label: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class OTPItem(BaseModel):
    emailId: str
    service: str
    code: str
    expires: str
    subject: Optional[str] = ""

class SummarizeIn(BaseModel):
    id: Optional[str] = None
    sender: str
    subject: Optional[str] = ""
    snippet: Optional[str] = ""
    body: Optional[str] = ""

class DeleteIn(BaseModel):
    id: str

class StatsOut(BaseModel):
    total: int
    spam: int
    phishing: int
    high_priority: int
    subscriptions: int
    work: int
    travel: int
    otp: int


# ─── DB session dependency ────────────────────────────────────────

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ─── Utility helpers ──────────────────────────────────────────────

def clean_sender(sender: str) -> str:
    """'Google <noreply@google.com>' → 'Google'"""
    name = re.sub(r"<.*?>", "", sender or "").strip()
    return name if name else (sender or "Unknown")

def extract_otp_code(text: str) -> Optional[str]:
    """Pull the first 4–8 digit number from text."""
    m = re.search(r'\b(\d{4,8})\b', text or "")
    return m.group(1) if m else None

def detect_otp_category(sender: str, subject: str, body: str) -> str:
    """
    Fine-grained category used by the popup UI.
    Returns one of: otp | travel | work | promo | spam | normal
    """
    text = f"{subject} {body}".lower()

    otp_keywords = [
        "otp", "one-time", "one time", "verification code", "sign-in code",
        "login code", "passcode", "security code", "authentication code",
        "2fa", "two-factor", "your code is", "your pin is",
    ]
    travel_keywords = [
        "flight", "booking confirmed", "ticket", "pnr", "boarding pass",
        "check-in", "hotel reservation", "train ticket", "bus ticket",
        "itinerary", "departure", "arrival gate", "seat number",
        "movie ticket", "event ticket", "concert", "bookmyshow",
    ]
    work_keywords = [
        "offer letter", "joining", "appointment letter", "salary", "payroll",
        "hr ", "human resources", "your manager", "performance review",
        "leave approved", "attendance", "payslip", "invoice", "purchase order",
    ]
    promo_keywords = ["sale", "discount", "offer", "deal", "coupon", "limited time"]
    spam_keywords  = ["lottery", "win money", "prize", "free gift", "congratulations you"]

    if any(kw in text for kw in otp_keywords) and re.search(r'\b\d{4,8}\b', text):
        return "otp"
    if any(kw in text for kw in travel_keywords):
        return "travel"
    if any(kw in text for kw in work_keywords):
        return "work"
    if any(kw in text for kw in spam_keywords):
        return "spam"
    if any(kw in text for kw in promo_keywords):
        return "promo"
    return "normal"


# ─── Routes ──────────────────────────────────────────────────────

@app.get("/ping")
def ping():
    return {"status": "ok"}


@app.get("/health")
def health():
    """Alias so both /ping and /health work (popup checks /health)."""
    return {"status": "ok"}


@app.post("/analyze", response_model=EmailOut)
def analyze_email(payload: EmailIn, db: Session = Depends(get_db)):
    sender  = payload.sender
    body    = payload.body
    subject = payload.subject or ""
    snippet = payload.snippet or ""

    # Watchlist override
    wl = db.query(Watchlist).filter(Watchlist.email == sender).first()

    # Rule-based analysis (your original logic, untouched)
    auto_category  = detect_category(sender, subject, body)
    auto_priority  = classify_priority(sender, subject, body)
    is_spam_rule, is_phishing = detect_spam_and_phishing(sender, subject, body)
    is_subscription, subscription_type, has_hidden_fees = detect_subscription_and_fees(
        sender, subject, body
    )

    # Fine-grained category for the popup
    otp_cat = detect_otp_category(sender, subject, body)

    # ML classifier
    ml_label = None
    if CLASSIFIER is not None:
        text_for_model = f"{subject} {body}"
        try:
            ml_label = CLASSIFIER.predict([text_for_model])[0]
        except Exception as e:
            print("Email classifier error:", e)

    if ml_label == "subscription_hidden_fee":
        is_subscription = True
        has_hidden_fees = True

    # Final category/priority
    if wl:
        category = wl.category or auto_category
        priority = "High"
    else:
        category = auto_category
        priority = auto_priority

    summary = f"Email from {clean_sender(sender)} categorized as {category}, priority {priority}."

    # Save log
    log = EmailLog(
        sender   = sender,
        body     = body,
        category = category,
        priority = priority,
        ml_label = ml_label,
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    return EmailOut(
        category        = category,
        priority        = priority,
        summary         = summary,
        is_spam         = is_spam_rule,
        is_phishing     = is_phishing,
        is_subscription = is_subscription,
        has_hidden_fees = has_hidden_fees,
        otp_category    = otp_cat,
        ml_label        = ml_label,
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


@app.get("/stats", response_model=StatsOut)
def stats(db: Session = Depends(get_db)):
    """
    Returns inbox category counts for the popup Overview tab.
    Uses the EmailLog table that /analyze already populates.
    """
    all_logs = db.query(EmailLog).all()

    total         = len(all_logs)
    spam          = sum(1 for l in all_logs if "spam"   in (l.category or "").lower() or (l.ml_label or "") == "spam")
    phishing      = sum(1 for l in all_logs if "phish"  in (l.category or "").lower())
    high_priority = sum(1 for l in all_logs if (l.priority or "").lower() == "high")
    subscriptions = sum(1 for l in all_logs if "subscri" in (l.category or "").lower() or (l.ml_label or "") == "subscription_hidden_fee")

    # Fine-grained counts — rerun detect_otp_category on stored data
    work   = 0
    travel = 0
    otp    = 0
    for log in all_logs:
        cat = detect_otp_category(log.sender or "", log.category or "", log.body or "")
        if cat == "work":   work   += 1
        elif cat == "travel": travel += 1
        elif cat == "otp":    otp    += 1

    return StatsOut(
        total         = total,
        spam          = spam,
        phishing      = phishing,
        high_priority = high_priority,
        subscriptions = subscriptions,
        work          = work,
        travel        = travel,
        otp           = otp,
    )


@app.post("/summarize")
def summarize(payload: SummarizeIn):
    """
    Returns a plain-English summary of an email.

    This is rule-based extraction for the MVP.
    To upgrade: replace the body of this function with a call to the
    Anthropic API (claude-haiku-4-5 is fast and cheap for this task).

    Example upgrade (requires: pip install anthropic):

        import anthropic
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{
                "role": "user",
                "content": f"Summarize this email in 2-3 sentences:\\n\\nFrom: {payload.sender}\\nSubject: {payload.subject}\\n\\n{payload.body or payload.snippet}"
            }]
        )
        summary = msg.content[0].text
        return {"summary": summary}
    """
    name    = clean_sender(payload.sender)
    subject = payload.subject or ""
    content = (payload.body or payload.snippet or "").replace("\u200c", "").strip()

    parts = []
    if subject:
        parts.append(f"Subject: {subject}.")
    if content:
        short = content[:300]
        parts.append(short + ("…" if len(content) > 300 else ""))
    if not parts:
        parts.append("No readable content found in this email.")

    return {"summary": f"From {name}. " + " ".join(parts)}


@app.get("/otps")
def get_otps(db: Session = Depends(get_db)):
    """
    Returns emails that contain OTP / one-time codes.
    Scans the EmailLog table for entries with otp_category == 'otp'.
    """
    all_logs = db.query(EmailLog).order_by(EmailLog.created_at.desc()).limit(100).all()

    otps = []
    for log in all_logs:
        cat = detect_otp_category(log.sender or "", log.category or "", log.body or "")
        if cat != "otp":
            continue
        code = extract_otp_code(log.body or "")
        if not code:
            continue
        otps.append({
            "emailId": str(log.id),
            "service": clean_sender(log.sender or ""),
            "code":    code,
            "expires": "expires soon",
            "subject": log.category,   # EmailLog doesn't store subject, use category as label
        })

    return {"otps": otps[:20]}


@app.post("/delete_email")
def delete_email(payload: DeleteIn, db: Session = Depends(get_db)):
    """
    Deletes an EmailLog entry by id.
    Also attempts to trash the email in Gmail if OAuth is configured.
    """
    try:
        record = db.query(EmailLog).filter(EmailLog.id == int(payload.id)).first()
        if record:
            db.delete(record)
            db.commit()
    except Exception as e:
        print(f"DB delete error: {e}")
        return {"success": False, "error": str(e)}

    # Best-effort Gmail trash
    try:
        from gmail_service import get_gmail_service
        svc = get_gmail_service()
        svc.users().messages().trash(userId="me", id=payload.id).execute()
    except Exception:
        pass   # Gmail OAuth not set up yet — that is fine

    return {"success": True}


# ─── Original rule-based helpers (unchanged from your code) ──────

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

    social_domains  = ["linkedin.com", "facebookmail.com", "instagram.com", "twitter.com", "x.com"]
    social_keywords = ["liked your post", "commented on", "followed you", "connection request"]
    if any(d in sender_lower for d in social_domains) or any(k in text for k in social_keywords):
        score -= 1

    service_domains  = ["accounts.google.com", "youtube.com", "google.com"]
    policy_keywords  = [
        "terms of service", "community guidelines", "privacy policy",
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

    social_domains  = ["linkedin.com", "facebookmail.com", "instagram.com", "twitter.com", "x.com"]
    social_keywords = [
        "liked your post", "commented on", "mentioned you", "connection request",
        "followed you", "new follower", "people you may know", "suggested for you",
    ]
    if any(d in sender_lower for d in social_domains) or any(k in text for k in social_keywords):
        return "Social"

    service_domains  = ["accounts.google.com", "youtube.com", "google.com"]
    service_keywords = [
        "terms of service", "community guidelines", "privacy policy",
        "mandatory email service announcement", "security alert", "policy update",
    ]
    if any(d in sender_lower for d in service_domains) and any(k in text for k in service_keywords):
        return "Notifications"

    work_keywords = ["meeting", "project", "deadline", "client", "task", "assignment"]
    if any(w in text for w in work_keywords):
        return "Work"

    transaction_keywords = ["invoice", "payment", "transaction", "receipt", "order", "purchase"]
    if any(w in text for w in transaction_keywords):
        return "Transactions"

    notification_keywords = ["notification", "alert", "login", "security", "otp", "verification code"]
    if any(w in text for w in notification_keywords):
        return "Notifications"

    promo_keywords = [
        "sale", "discount", "offer", "deal", "coupon", "limited time",
        "hiring for", "apply now", "followers", "suggested for you",
    ]
    if any(w in text for w in promo_keywords):
        return "Promotions"

    personal_keywords = ["dear", "hi ", "hello", "regards", "thank you"]
    if any(w in text for w in personal_keywords):
        return "Personal"

    return "General"


def detect_spam_and_phishing(sender: str, subject: str, body: str) -> tuple:
    text = f"{subject} {body}".lower()
    sender_lower = sender.lower()

    is_spam     = False
    is_phishing = False

    spam_keywords = ["lottery", "win money", "prize", "free gift", "congratulations"]
    if any(w in text for w in spam_keywords):
        is_spam = True

    phishing_keywords = [
        "verify your account", "update your account", "suspend your account",
        "login to continue", "confirm your password", "confirm your identity",
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


def detect_subscription_and_fees(sender: str, subject: str, body: str) -> tuple:
    text = f"{subject} {body}".lower()
    sender_lower = sender.lower()

    is_subscription  = False
    subscription_type = "Unknown"
    has_hidden_fees  = False

    subscription_keywords = [
        "subscription", "auto-renew", "billing cycle", "plan will renew",
        "renewal", "trial period", "your plan will be renewed",
    ]
    if any(w in text for w in subscription_keywords):
        is_subscription = True

    streaming_domains = ["netflix", "primevideo", "spotify", "youtube", "hotstar"]
    if any(d in sender_lower for d in streaming_domains):
        is_subscription  = True
        subscription_type = "Streaming"

    edu_domains = ["coursera", "udemy", "byjus", "unacademy", "thinkific"]
    if any(d in sender_lower for d in edu_domains):
        is_subscription  = True
        subscription_type = "Education"

    hidden_fee_phrases = [
        "after the trial period you will be charged",
        "introductory price", "standard price",
        "additional charges may apply", "taxes extra",
        "terms and conditions apply",
    ]
    if any(p in text for p in hidden_fee_phrases):
        has_hidden_fees = True
        is_subscription = True

    return is_subscription, subscription_type, has_hidden_fees