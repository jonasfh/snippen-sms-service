-- Migration: 0004_messages_booking_context
-- Description: Add booking_id and conversation_id columns to messages, and create conversation_contexts table

ALTER TABLE messages ADD COLUMN booking_id TEXT;
ALTER TABLE messages ADD COLUMN conversation_id INTEGER;

CREATE INDEX IF NOT EXISTS idx_messages_booking_id ON messages(booking_id);
CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);

CREATE TABLE IF NOT EXISTS conversation_contexts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone_number TEXT NOT NULL UNIQUE,
    active_booking_id TEXT,
    pending_booking_ids TEXT,
    pending_message_id INTEGER,
    state TEXT NOT NULL DEFAULT 'idle',
    last_activity_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    modified_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_conv_contexts_phone ON conversation_contexts(phone_number);
CREATE INDEX IF NOT EXISTS idx_conv_contexts_state ON conversation_contexts(state);
