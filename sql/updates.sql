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
