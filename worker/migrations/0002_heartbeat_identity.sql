-- FIX-B: heartbeat carries the CONNECTED account identity, not just the mode
ALTER TABLE heartbeat ADD COLUMN loginid TEXT;
ALTER TABLE heartbeat ADD COLUMN currency TEXT;
