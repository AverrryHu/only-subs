-- Add user info columns to channels table
ALTER TABLE channels ADD COLUMN IF NOT EXISTS user_email TEXT;
ALTER TABLE channels ADD COLUMN IF NOT EXISTS user_name TEXT;

-- Make user_id unique per user info (optional - for tracking user info)
-- This helps us store user email/name once per user
