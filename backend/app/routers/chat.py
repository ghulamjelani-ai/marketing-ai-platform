import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core import ratelimit
from app.core.openai_client import generate_marketing_ai_reply
from app.db.database import get_db
from app.models.models import Conversation, Message, User
from app.routers.auth import get_current_db_user
from app.routers.memory import get_memory_text, update_memory_in_background
from app.schemas.chat import ChatRequest, ChatResponse, ChatHistoryResponse

router = APIRouter()


def find_conversation(db: Session, user: User, conversation_id: str | None):
    """The user's conversation with this id, or None (also for an id that is not valid,
    for example an old value left in the browser)."""

    try:
        key = uuid.UUID(str(conversation_id))
    except ValueError:
        return None

    return (
        db.query(Conversation)
        .filter(Conversation.id == key, Conversation.user_id == user.id)
        .first()
    )


@router.post("/plan", response_model=ChatResponse)
def generate_marketing_plan(
    data: ChatRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_db_user),
):
    ratelimit.check(user.id, "chat")

    if data.conversation_id:
        conversation = find_conversation(db, user, data.conversation_id)

        if not conversation:
            raise HTTPException(
                status_code=404,
                detail="Conversation not found"
            )
    else:
        title = data.message[:60] if data.message else "New Marketing Chat"

        conversation = Conversation(
            user_id=user.id,
            title=title,
        )

        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    # Earlier messages give the model context for follow-up questions.
    previous_messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.asc())
        .all()
    )

    history = [
        {
            "role": "assistant" if message.role == "ai" else "user",
            "content": message.content,
        }
        for message in previous_messages
    ][-12:]

    user_message = Message(
        conversation_id=conversation.id,
        role="user",
        content=data.message,
    )

    db.add(user_message)
    db.commit()

    reply = generate_marketing_ai_reply(
        user_message=data.message,
        business_name=data.business_name or "My Business",
        industry=data.industry,
        history=history,
        memory=get_memory_text(db, user.id),
    )

    ai_message = Message(
        conversation_id=conversation.id,
        role="ai",
        content=reply,
    )

    db.add(ai_message)
    db.commit()
    db.refresh(conversation)

    # Remember lasting business facts from this message (runs after the reply is sent).
    background_tasks.add_task(update_memory_in_background, user.id, data.message)

    return ChatResponse(
        reply=reply,
        conversation_id=str(conversation.id),
    )


@router.get(
    "/history/{conversation_id}",
    response_model=ChatHistoryResponse
)
def get_chat_history(
    conversation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_db_user),
):
    conversation = find_conversation(db, user, conversation_id)

    if not conversation:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found"
        )

    return ChatHistoryResponse(
        conversation_id=str(conversation.id),
        title=conversation.title,
        messages=[
            {
                "role": message.role,
                "content": message.content,
            }
            for message in conversation.messages
        ],
    )


@router.get("/conversations")
def get_conversations(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_db_user),
):
    conversations = (
        db.query(Conversation)
        .filter(Conversation.user_id == user.id)
        .order_by(Conversation.updated_at.desc())
        .all()
    )

    return {
        "success": True,
        "conversations": [
            {
                "id": str(conversation.id),
                "title": conversation.title,
                "created_at": conversation.created_at.isoformat(),
                "updated_at": conversation.updated_at.isoformat(),
            }
            for conversation in conversations
        ],
    }


@router.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_db_user),
):
    conversation = find_conversation(db, user, conversation_id)

    if not conversation:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found"
        )

    db.delete(conversation)
    db.commit()

    return {"success": True}

