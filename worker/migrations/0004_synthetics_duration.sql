-- Support flexible trade duration for synthetic indices (seconds, minutes)
ALTER TABLE pairs ADD COLUMN duration INTEGER DEFAULT 15;
ALTER TABLE pairs ADD COLUMN duration_unit TEXT DEFAULT 'm';
