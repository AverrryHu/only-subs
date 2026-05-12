-- Add user email and name to user_settings table
ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS user_email TEXT;
ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS user_name TEXT;