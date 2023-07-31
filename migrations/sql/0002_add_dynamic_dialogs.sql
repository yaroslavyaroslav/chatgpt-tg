ALTER TABLE chatgpttg.user ADD COLUMN IF NOT EXISTS dynamic_dialog BOOLEAN DEFAULT FALSE;

ALTER TABLE chatgpttg.message ADD COLUMN IF NOT EXISTS activation_dtime TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW();
ALTER TABLE chatgpttg.dialog DROP COLUMN IF EXISTS model;
