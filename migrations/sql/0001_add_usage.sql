CREATE SCHEMA IF NOT EXISTS chatgpttg;

CREATE TABLE IF NOT EXISTS chatgpttg.completion_usage
(
    id bigserial PRIMARY KEY,
    user_id bigserial NOT NULL,
    prompt_tokens int NOT NULL,
    completion_tokens int NOT NULL,
    total_tokens int NOT NULL,
    model text NOT NULL,
    cdate timestamp WITH TIME ZONE NOT NULL default NOW()
);

CREATE INDEX completion_usage_user_id_idx ON chatgpttg.completion_usage USING hash(user_id);
