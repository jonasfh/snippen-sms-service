-- Migration: 0003_messages_external_id
-- Description: Add external_id column and index to messages table for external system synchronization

ALTER TABLE messages ADD COLUMN external_id TEXT;

CREATE INDEX IF NOT EXISTS idx_messages_external_id ON messages(external_id);
