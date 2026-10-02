from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import CheckConstraint


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


db = SQLAlchemy()


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(40), unique=True, nullable=False)
    email = db.Column(db.String(254), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    conversations = db.relationship(
        "Conversation",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="Conversation.updated_at.desc()",
    )


class Conversation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    title = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    user = db.relationship("User", back_populates="conversations")
    messages = db.relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by=lambda: (Message.created_at.asc(), Message.id.asc()),
    )


class Message(db.Model):
    __table_args__ = (
        CheckConstraint("sender IN ('user', 'saathi')", name="valid_message_sender"),
    )

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(
        db.Integer,
        db.ForeignKey("conversation.id"),
        nullable=False,
        index=True,
    )
    sender = db.Column(db.String(10), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    conversation = db.relationship("Conversation", back_populates="messages")


class Memory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    content = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(32), nullable=False, default="interest")
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    user = db.relationship("User", backref=db.backref("memories", cascade="all, delete-orphan"))


class CheckIn(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    mood = db.Column(db.String(30), nullable=False)
    note = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    user = db.relationship("User", backref=db.backref("check_ins", cascade="all, delete-orphan"))


class TrustedContact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, unique=True, index=True)
    label = db.Column(db.String(80), nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    user = db.relationship("User", backref=db.backref("trusted_contact", uselist=False, cascade="all, delete-orphan"))