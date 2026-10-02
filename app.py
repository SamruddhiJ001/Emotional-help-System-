from datetime import date, timedelta
from functools import wraps
import logging
import os
import re
import secrets
import time

from dotenv import load_dotenv
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import check_password_hash, generate_password_hash

from models import CheckIn, Conversation, Memory, Message, TrustedContact, User, db, utc_now
from services.ai_service import AIService, analyze_safety, generate_demo_response

load_dotenv()


app = Flask(__name__, instance_relative_config=True)
os.makedirs(app.instance_path, exist_ok=True)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
    SQLALCHEMY_DATABASE_URI="sqlite:///saathi.db",
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE") == "1",
    AI_PROVIDER=os.environ.get("AI_PROVIDER", "demo"),
    MAX_AI_REQUESTS_PER_MINUTE=int(os.environ.get("MAX_AI_REQUESTS_PER_MINUTE", "20") or "20"),
)

if not os.environ.get("SECRET_KEY"):
    logging.warning("Using the local development SECRET_KEY. Set SECRET_KEY before deployment.")

db.init_app(app)


def initialize_database():
    try:
        with app.app_context():
            db.create_all()
    except SQLAlchemyError:
        logging.exception("Could not initialize the SAATHI database.")


initialize_database()


@app.errorhandler(SQLAlchemyError)
def handle_database_error(error):
    db.session.rollback()
    logging.error("A database operation failed: %s", error.__class__.__name__)
    if request.path.startswith("/api/"):
        return jsonify(error="The database is temporarily unavailable. Please try again."), 503
    return "The database is temporarily unavailable. Please try again.", 503


@app.get("/")
def home():
    user = current_user()
    if user is not None:
        contact = TrustedContact.query.filter_by(user_id=user.id).first()
        latest_check_in = CheckIn.query.filter_by(user_id=user.id).order_by(CheckIn.created_at.desc()).first()
        memories = Memory.query.filter_by(user_id=user.id).order_by(Memory.created_at.desc()).limit(3).all()
        return render_template("dashboard.html", current_user=user, trusted_contact=contact, latest_check_in=latest_check_in, memories=memories)
    return render_template("index.html", current_user=user)


def current_user():
    user_id = session.get("user_id")
    if user_id is None:
        return None
    user = db.session.get(User, user_id)
    if user is None:
        session.clear()
    return user


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if current_user() is None:
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped_view


@app.get("/profile")
@login_required
def profile_view():
    user = current_user()
    contact = TrustedContact.query.filter_by(user_id=user.id).first()
    return render_template("profile.html", current_user=user, trusted_contact=contact)


def make_conversation(user):
    conversation = Conversation(
        user=user,
        title=f"Conversation — {date.today().strftime('%B %d').replace(' 0', ' ')}",
    )
    db.session.add(conversation)
    db.session.commit()
    return conversation


def conversation_sections(conversations):
    today = date.today()
    yesterday = today - timedelta(days=1)
    sections = {"Today": [], "Yesterday": [], "Older conversations": []}
    for conversation in conversations:
        updated_day = conversation.updated_at.date()
        if updated_day == today:
            sections["Today"].append(conversation)
        elif updated_day == yesterday:
            sections["Yesterday"].append(conversation)
        else:
            sections["Older conversations"].append(conversation)
    return sections


def render_chat_page(user, active_conversation):
    conversations = (
        Conversation.query
        .filter_by(user_id=user.id)
        .order_by(Conversation.updated_at.desc())
        .all()
    )
    return render_template(
        "chat.html",
        current_user=user,
        conversation=active_conversation,
        conversations=conversations,
        conversation_sections=conversation_sections(conversations),
    )


@app.get("/register")
def register():
    if current_user() is not None:
        return redirect(url_for("chat"))
    return render_template("register.html")


@app.post("/register")
def register_submit():
    if current_user() is not None:
        return redirect(url_for("chat"))

    username = request.form.get("username", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not username or not email or not password or not confirm_password:
        flash("Please complete every field.", "error")
    elif len(username) < 2 or len(username) > 40:
        flash("Your name must be between 2 and 40 characters.", "error")
    elif not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        flash("Enter a valid email address.", "error")
    elif len(password) < 8:
        flash("Choose a password with at least 8 characters.", "error")
    elif password != confirm_password:
        flash("Those passwords do not match.", "error")
    elif User.query.filter(func.lower(User.username) == username.casefold()).first():
        flash("That username is already in use. Try another one.", "error")
    elif User.query.filter_by(email=email).first():
        flash("That email is already registered. Try logging in.", "error")
    else:
        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
        )
        db.session.add(user)
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            flash("We couldn't create your account just now. Please try again.", "error")
        else:
            flash("Your account is ready. Please log in.", "success")
            return redirect(url_for("login"))

    return render_template("register.html"), 400


@app.get("/login")
def login():
    if current_user() is not None:
        return redirect(url_for("chat"))
    return render_template("login.html")


@app.post("/login")
def login_submit():
    if current_user() is not None:
        return redirect(url_for("chat"))

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    user = User.query.filter_by(email=email).first()
    if user is None or not check_password_hash(user.password_hash, password):
        flash("Email or password is incorrect.", "error")
        return render_template("login.html"), 401

    session.clear()
    session["user_id"] = user.id
    return redirect(url_for("chat"))


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.get("/chat")
@login_required
def chat():
    user = current_user()
    conversation = (
        Conversation.query
        .filter_by(user_id=user.id)
        .order_by(Conversation.updated_at.desc())
        .first()
    )
    if conversation is None:
        conversation = make_conversation(user)
    return render_chat_page(user, conversation)


@app.post("/chat/new")
@login_required
def new_chat():
    conversation = make_conversation(current_user())
    return redirect(url_for("chat_conversation", conversation_id=conversation.id))


@app.get("/chat/<int:conversation_id>")
@login_required
def chat_conversation(conversation_id):
    user = current_user()
    conversation = Conversation.query.filter_by(
        id=conversation_id,
        user_id=user.id,
    ).first_or_404()
    return render_chat_page(user, conversation)


def demo_response(message, mode, kind):
    return generate_demo_response(message, mode, kind)


@app.post("/api/chat")
def api_chat():
    user = current_user()
    if user is None:
        return jsonify(error="Please log in to continue."), 401

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="Send a message to continue."), 400

    message_text = payload.get("message", "")
    if not isinstance(message_text, str) or not message_text.strip():
        return jsonify(error="Write a message before sending."), 400
    message_text = message_text.strip()
    if len(message_text) > 1000:
        return jsonify(error="Messages must be 1,000 characters or fewer."), 400

    conversation_id = payload.get("conversation_id")
    if isinstance(conversation_id, bool) or not isinstance(conversation_id, int):
        return jsonify(error="This conversation could not be found."), 404
    conversation = Conversation.query.filter_by(
        id=conversation_id,
        user_id=user.id,
    ).first()
    if conversation is None:
        return jsonify(error="This conversation could not be found."), 404

    rate_limit = int(app.config.get("MAX_AI_REQUESTS_PER_MINUTE", "20") or "20")
    request_times = session.get("ai_request_times", [])
    current_time = time.time()
    request_times = [stamp for stamp in request_times if current_time - stamp < 60]
    if len(request_times) >= rate_limit:
        return jsonify(error="Please give me a moment before sending another message."), 429
    request_times.append(current_time)
    session["ai_request_times"] = request_times

    mode = payload.get("mode", "talk")
    if not isinstance(mode, str) or mode not in {"talk", "light", "focus", "calm"}:
        mode = "talk"
    kind = "story" if payload.get("kind") == "story" else "message"

    safety = analyze_safety(message_text)
    now = utc_now()
    user_message = Message(conversation=conversation, sender="user", content=message_text, created_at=now)
    db.session.add(user_message)
    db.session.flush()

    ai_service = AIService()
    response_text = (
        safety["response"]
        if safety["triggered"]
        else ai_service.generate_response(
            user_message=message_text,
            conversation=conversation,
            mode=mode,
            kind=kind,
        )
    )

    saathi_message = Message(conversation=conversation, sender="saathi", content=response_text, created_at=now)
    db.session.add(saathi_message)
    conversation.updated_at = now
    db.session.commit()

    return jsonify(
        success=True,
        user_message={"sender": "user", "content": message_text},
        reply={"sender": "saathi", "content": response_text},
        safety=safety,
    )


@app.post("/api/memories/save")
@login_required
def save_memory_api():
    payload = request.get_json(silent=True) or {}
    content = (payload.get("content") or "").strip()
    if not content:
        return jsonify(error="Nothing to save yet."), 400
    category = str(payload.get("category") or "interest").strip() or "interest"
    if category not in {"interest", "goal", "preference", "important_note"}:
        category = "interest"
    memory = Memory(user=current_user(), content=content, category=category)
    db.session.add(memory)
    db.session.commit()
    return jsonify(success=True, message="Got it — I'll remember that.")


@app.get("/memories")
@login_required
def memories_page():
    memories = Memory.query.filter_by(user_id=current_user().id).order_by(Memory.created_at.desc()).all()
    return render_template("memories.html", current_user=current_user(), memories=memories)


@app.post("/memories/delete/<int:memory_id>")
@login_required
def delete_memory(memory_id):
    memory = Memory.query.filter_by(id=memory_id, user_id=current_user().id).first_or_404()
    db.session.delete(memory)
    db.session.commit()
    flash("Memory deleted.", "success")
    return redirect(url_for("memories_page"))


@app.post("/memories/forget-all")
@login_required
def forget_all_memories():
    Memory.query.filter_by(user_id=current_user().id).delete()
    db.session.commit()
    flash("All memories were cleared.", "success")
    return redirect(url_for("memories_page"))


@app.get("/check-in")
@login_required
def check_in_page():
    user = current_user()
    today = date.today()
    today_check_in = CheckIn.query.filter_by(user_id=user.id).filter(func.date(CheckIn.created_at) == today).first()
    return render_template("check_in.html", current_user=user, today_check_in=today_check_in)


@app.post("/check-in")
@login_required
def submit_check_in():
    mood = request.form.get("mood", "").strip()
    note = request.form.get("note", "").strip()
    valid_moods = {"good": "😊 Good", "okay": "🙂 Okay", "not-great": "😐 Not great", "difficult": "😟 Difficult", "very-difficult": "😞 Very difficult"}
    if mood not in valid_moods:
        flash("Please choose a mood.", "error")
        return redirect(url_for("check_in_page"))
    user = current_user()
    today = date.today()
    existing = CheckIn.query.filter_by(user_id=user.id).filter(func.date(CheckIn.created_at) == today).first()
    if existing is not None:
        flash("You’ve already checked in today. Thank you for staying aware of your day.", "success")
        return redirect(url_for("check_in_page"))
    check_in = CheckIn(user_id=user.id, mood=mood, note=note or None)
    db.session.add(check_in)
    db.session.commit()
    flash("Thanks for checking in with yourself today.", "success")
    return redirect(url_for("check_in_page"))


@app.get("/wellbeing")
@login_required
def wellbeing_page():
    user = current_user()
    check_ins = CheckIn.query.filter_by(user_id=user.id).order_by(CheckIn.created_at.desc()).all()
    mood_labels = {
        "good": "😊 Good",
        "okay": "🙂 Okay",
        "not-great": "😐 Not great",
        "difficult": "😟 Difficult",
        "very-difficult": "😞 Very difficult",
    }
    recent = []
    for check_in in check_ins:
        recent.append({
            "label": mood_labels.get(check_in.mood, check_in.mood),
            "date_label": check_in.created_at.strftime("%A" if check_in.created_at.date() != date.today() else "Today"),
            "note": check_in.note,
        })
    return render_template("wellbeing.html", current_user=user, check_ins=recent)


@app.get("/privacy")
@login_required
def privacy_page():
    return render_template("privacy.html", current_user=current_user())


@app.post("/privacy/delete-conversations")
@login_required
def delete_conversations():
    Conversation.query.filter_by(user_id=current_user().id).delete()
    db.session.commit()
    flash("Conversation history deleted.", "success")
    return redirect(url_for("privacy_page"))


@app.post("/privacy/delete-memories")
@login_required
def delete_user_memories():
    Memory.query.filter_by(user_id=current_user().id).delete()
    db.session.commit()
    flash("Memories deleted.", "success")
    return redirect(url_for("privacy_page"))


@app.post("/privacy/delete-checkins")
@login_required
def delete_checkins():
    CheckIn.query.filter_by(user_id=current_user().id).delete()
    db.session.commit()
    flash("Check-ins deleted.", "success")
    return redirect(url_for("privacy_page"))


@app.post("/privacy/delete-account")
@login_required
def delete_account():
    user = current_user()
    db.session.delete(user)
    db.session.commit()
    session.clear()
    flash("Your account has been deleted.", "success")
    return redirect(url_for("home"))


@app.get("/support")
@login_required
def support_page():
    return render_template("support.html", current_user=current_user())


@app.post("/profile/trusted-person")
@login_required
def save_trusted_person():
    label = request.form.get("label", "").strip()
    if not label:
        flash("Please add a trusted person label.", "error")
        return redirect(url_for("profile_view"))
    contact = TrustedContact.query.filter_by(user_id=current_user().id).first()
    if contact is None:
        contact = TrustedContact(user_id=current_user().id, label=label)
        db.session.add(contact)
    else:
        contact.label = label
    db.session.commit()
    flash("Trusted person saved.", "success")
    return redirect(url_for("profile_view"))


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
