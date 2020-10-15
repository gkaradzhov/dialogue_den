CREATE TABLE mturk_info(
id uuid NOT NULL,
assignment_id text,
user_id uuid,
campaign_id uuid,
hit_id text,
worker_id text,
redirect_url text
)

ALTER TABLE ONLY public.mturk_info
    ADD CONSTRAINT mturk_info_pkey PRIMARY KEY (id);




--- Update 12.06
ALTER TABLE mturk_info
ADD COLUMN qualification_granted bool DEFAULT false,
ADD COLUMN bonus_status text,
ADD COLUMN payment_status text;


-- Update 15.10

ALTER TABLE message
ADD COLUMN origin_type text;

ALTER TABLE campaign
ADD COLUMN user_moderator_chance float DEFAULT 0;