--
-- PostgreSQL database dump
--

-- Dumped from database version 11.5
-- Dumped by pg_dump version 12.2 (Ubuntu 12.2-2.pgdg18.04+1)

-- Started on 2020-02-25 13:22:01 GMT

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

DROP DATABASE dialogue_den;
--
-- TOC entry 3827 (class 1262 OID 16401)
-- Name: dialogue_den; Type: DATABASE; Schema: -; Owner: -
--

CREATE DATABASE dialogue_den WITH TEMPLATE = template0 ENCODING = 'UTF8' LC_COLLATE = 'en_US.UTF-8' LC_CTYPE = 'en_US.UTF-8';


\connect dialogue_den

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- TOC entry 198 (class 1259 OID 16491)
-- Name: campaign; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.campaign (
    id uuid NOT NULL,
    name text,
    is_active boolean DEFAULT false NOT NULL,
    start_threshold integer DEFAULT 3 NOT NULL,
    start_time integer DEFAULT 3 NOT NULL,
    close_threshold integer DEFAULT 5 NOT NULL
);


--
-- TOC entry 197 (class 1259 OID 16426)
-- Name: message; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.message (
    id uuid NOT NULL,
    origin text,
    origin_id text,
    message_type text,
    content text,
    "timestamp" timestamp with time zone,
    room_id uuid NOT NULL,
    user_status text
);


--
-- TOC entry 196 (class 1259 OID 16402)
-- Name: room; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.room (
    name text,
    id uuid NOT NULL,
    is_done boolean,
    campaign_id uuid,
    status text
);


--
-- TOC entry 3698 (class 2606 OID 16498)
-- Name: campaign campaign_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaign
    ADD CONSTRAINT campaign_pkey PRIMARY KEY (id);


--
-- TOC entry 3696 (class 2606 OID 16433)
-- Name: message message_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.message
    ADD CONSTRAINT message_pkey PRIMARY KEY (id);


--
-- TOC entry 3694 (class 2606 OID 16435)
-- Name: room room_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.room
    ADD CONSTRAINT room_pkey PRIMARY KEY (id);


--
-- TOC entry 3699 (class 2606 OID 16499)
-- Name: room fk_campaign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.room
    ADD CONSTRAINT fk_campaign FOREIGN KEY (campaign_id) REFERENCES public.campaign(id);


--
-- TOC entry 3700 (class 2606 OID 16436)
-- Name: message fk_room; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.message
    ADD CONSTRAINT fk_room FOREIGN KEY (room_id) REFERENCES public.room(id) NOT VALID;


-- Completed on 2020-02-25 13:22:03 GMT

--
-- PostgreSQL database dump complete
--

