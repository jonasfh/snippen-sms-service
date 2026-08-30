-- 0002_messages_modem_id_index.sql
-- Add index on modem_message_id for fast lookup and deduplication

CREATE INDEX IF NOT EXISTS idx_messages_modem_id ON messages(modem_message_id);
